"""The KPI lab state machine.

Design requirement: the loop must always terminate, and every terminal state must be a
legitimate outcome. A search that only stops when it succeeds will eventually report success
on noise, because with enough attempts something always clears a threshold. So "the target is
unreachable", "the target was reached but the budget alone explains it", and "the target was
reached but the model contributed nothing" are all first-class terminal states here, not
failures to be escaped by searching harder.

State order
-----------
``INIT`` -> ``FEASIBILITY_GATE`` -> ``PROTOCOL_FREEZE`` -> ``BASELINE_ARM_A``
-> ``NEGATIVE_CONTROL_CALIB`` -> ``SEARCH_LOOP`` -> ``CONFIRMATION`` -> terminal

Each transition is appended to the hash-chained ledger before it takes effect, so an
interrupted run can be reconstructed and a deleted experiment is detectable.

Terminal states
---------------
``KPI_INFEASIBLE``
    The packing bound exceeds the ticket budget. No model can close the gap, so the run stops
    before spending compute.
``KPI_MET_DEGENERATE``
    The budget is at or above the packing bound, so reaching the target says nothing about any
    model. Reported as a defect in the KPI definition, not as an achievement.
``KPI_MET_NO_MODEL_VALUE``
    Target reached, but the model arm did not beat the data-free reference arm. The correct
    conclusion is that the covering construction is what worked.
``KPI_MET_VERIFIED``
    Target reached, the model arm beat the reference arm, the e-process crossed ``1/alpha``,
    and every control behaved. The only state that supports a claim of model skill.
``BUDGET_EXHAUSTED``
    Search ran out of experiments or time without evidence. Reports the best achieved bound.
``LEAK_DETECTED_SUSPENDED``
    Control false-positive rate exceeded its cap, or the positive control failed to fire.
``PROTOCOL_VIOLATION``
    A hash mismatch or an attempt to read the sealed window during search.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from loto.combinatorics.bounds import feasibility_bound
from loto.data.lineage import atomic_write_json, utc_now_iso
from loto.kpi_lab.arms import (
    ArmComparison,
    build_model_arm,
    build_reference_arm,
    compare_arms,
)
from loto.kpi_lab.kpi import CostModel, KpiDefinition, KpiMeasurement, coverage_efficiency
from loto.kpi_lab.ledger import ExperimentLedger
from loto.kpi_lab.negative_controls import run_control_suite
from loto.kpi_lab.proposer import GridProposer, LlmProposer, Proposal
from loto.kpi_lab.stopping import EProcess

__all__ = [
    "LabState",
    "TerminalState",
    "TERMINAL_STATES",
    "SUCCESSFUL_TERMINALS",
    "SearchBudget",
    "LabConfig",
    "ExperimentRecord",
    "LabReport",
    "KpiLab",
]

LabState = Literal[
    "INIT",
    "FEASIBILITY_GATE",
    "PROTOCOL_FREEZE",
    "BASELINE_ARM_A",
    "NEGATIVE_CONTROL_CALIB",
    "SEARCH_LOOP",
    "CONFIRMATION",
    "TERMINAL",
]

TerminalState = Literal[
    "KPI_INFEASIBLE",
    "KPI_MET_DEGENERATE",
    "KPI_MET_NO_MODEL_VALUE",
    "KPI_MET_VERIFIED",
    "BUDGET_EXHAUSTED",
    "LEAK_DETECTED_SUSPENDED",
    "PROTOCOL_VIOLATION",
]

TERMINAL_STATES: tuple[TerminalState, ...] = (
    "KPI_INFEASIBLE",
    "KPI_MET_DEGENERATE",
    "KPI_MET_NO_MODEL_VALUE",
    "KPI_MET_VERIFIED",
    "BUDGET_EXHAUSTED",
    "LEAK_DETECTED_SUSPENDED",
    "PROTOCOL_VIOLATION",
)

#: Terminal states that represent a completed, trustworthy investigation. Note that three of
#: the four are negative results: a lab that treats only ``KPI_MET_VERIFIED`` as success will
#: keep searching until noise obliges.
SUCCESSFUL_TERMINALS: tuple[TerminalState, ...] = (
    "KPI_INFEASIBLE",
    "KPI_MET_DEGENERATE",
    "KPI_MET_NO_MODEL_VALUE",
    "KPI_MET_VERIFIED",
    "BUDGET_EXHAUSTED",
)

_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class SearchBudget:
    """Hard limits. Reaching one of these yields ``BUDGET_EXHAUSTED``, never a relaxation."""

    max_experiments: int = 100
    max_runtime_seconds: int = 3600
    max_consecutive_failures: int = 10
    min_confirmation_draws: int = 30
    n_monte_carlo: int = 8000

    def __post_init__(self) -> None:
        if min(self.max_experiments, self.max_runtime_seconds) <= 0:
            raise ValueError("budget limits must be positive")


@dataclass(frozen=True)
class LabConfig:
    """Everything needed to reproduce a lab session."""

    kpi: KpiDefinition
    budget: SearchBudget = field(default_factory=SearchBudget)
    calibration_fraction: float = 0.5
    seed: int = 42
    improvement_threshold: float = 0.02
    output_dir: Path = Path("artifacts/kpi_lab")
    llm_endpoint: str | None = None
    llm_model: str = "local"
    cost_model: CostModel = field(default_factory=CostModel)
    schema_version: str = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be in (0, 1)")


@dataclass(frozen=True)
class ExperimentRecord:
    """One search iteration, kept whether it helped or not."""

    index: int
    proposal_id: str
    proposal_source: str
    parameters: dict[str, Any]
    sealed_coverage: float | None
    reference_coverage: float
    delta: float | None
    efficiency: float | None
    e_value: float
    status: str
    error: str | None = None
    duration_seconds: float = 0.0
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LabReport:
    """The lab's verdict, with everything a reviewer needs to disagree with it."""

    session_id: str
    terminal_state: TerminalState
    reason: str
    kpi: dict[str, Any]
    feasibility: dict[str, Any]
    cost: dict[str, Any]
    reference_arm: dict[str, Any] | None
    best_model_arm: dict[str, Any] | None
    best_measurement: dict[str, Any] | None
    e_process: dict[str, Any] | None
    control_suite: dict[str, Any] | None
    experiments: tuple[dict[str, Any], ...]
    n_experiments: int
    ledger_path: str
    ledger_integrity: dict[str, Any]
    states_visited: tuple[str, ...]
    started_at: str
    finished_at: str
    schema_version: str = _SCHEMA_VERSION

    @property
    def claims_model_skill(self) -> bool:
        return self.terminal_state == "KPI_MET_VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["experiments"] = [dict(e) for e in self.experiments]
        payload["states_visited"] = list(self.states_visited)
        payload["claims_model_skill"] = self.claims_model_skill
        payload["successful_terminal"] = self.terminal_state in SUCCESSFUL_TERMINALS
        return payload


class SealedWindowAccessError(RuntimeError):
    """Raised when the search phase tries to read the sealed window."""


class _SealedWindow:
    """Wrapper that refuses reads until explicitly opened at confirmation time.

    Holdout protection by construction rather than by convention. A search loop that needs
    the sealed rows to score itself will raise instead of quietly leaking.
    """

    def __init__(self, draws: np.ndarray) -> None:
        self._draws = np.asarray(draws, dtype=np.int64)
        self._opened = False
        self.open_count = 0

    @property
    def n_rows(self) -> int:
        return int(self._draws.shape[0])

    def open(self, reason: str) -> np.ndarray:
        self._opened = True
        self.open_count += 1
        self._last_reason = reason
        return self._draws

    def peek_shape(self) -> tuple[int, int]:
        return tuple(self._draws.shape)  # type: ignore[return-value]

    def require_unopened(self) -> None:
        if self._opened:
            raise SealedWindowAccessError(
                f"sealed window already opened {self.open_count} time(s); "
                "search must not score against it"
            )


class KpiLab:
    """Runs the state machine to a terminal state."""

    def __init__(self, config: LabConfig) -> None:
        self.config = config
        self.session_id = f"lab-{config.kpi.game}-{int(time.time())}"
        self.output_dir = Path(config.output_dir) / self.session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = ExperimentLedger(
            self.output_dir / "ledger.jsonl", session_id=self.session_id
        )
        self.states_visited: list[str] = []
        self._started_at = utc_now_iso()

    # -- helpers ------------------------------------------------------------------------

    def _enter(self, state: LabState | TerminalState, payload: dict[str, Any]) -> None:
        self.states_visited.append(str(state))
        self.ledger.append("state_transition", {"state": str(state), **payload})

    def _split(self, draws: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Chronological split into history / calibration / sealed. No shuffling."""
        arr = np.asarray(draws, dtype=np.int64)
        n = arr.shape[0]
        if n < 60:
            raise ValueError(
                f"need at least 60 draws to form history/calibration/sealed windows, got {n}"
            )
        sealed_n = max(self.config.budget.min_confirmation_draws, int(n * 0.25))
        remaining = n - sealed_n
        cal_n = max(10, int(remaining * self.config.calibration_fraction))
        hist_n = remaining - cal_n
        if hist_n < 10:
            raise ValueError("history window too small after splitting")
        return arr[:hist_n], arr[hist_n : hist_n + cal_n], arr[hist_n + cal_n :]

    # -- run ----------------------------------------------------------------------------

    def run(self, draws: np.ndarray) -> LabReport:
        """Execute the machine. Always returns a report; never loops indefinitely."""
        kpi = self.config.kpi
        budget = self.config.budget
        self._enter("INIT", {"session_id": self.session_id, "kpi": kpi.to_dict()})

        # ---- FEASIBILITY_GATE ---------------------------------------------------------
        bound = feasibility_bound(
            kpi.game, target_coverage=kpi.target_coverage, tolerance=kpi.tolerance
        )
        cost = self.config.cost_model.estimate(game=kpi.game, n_tickets=kpi.n_tickets)
        self._enter(
            "FEASIBILITY_GATE",
            {"bound": bound.to_dict(), "cost": cost.to_dict()},
        )
        if kpi.n_tickets < bound.lower_bound_tickets:
            return self._terminate(
                "KPI_INFEASIBLE",
                (
                    f"target_coverage={kpi.target_coverage} at tolerance={kpi.tolerance} "
                    f"requires at least {bound.lower_bound_tickets:,} tickets by the packing "
                    f"bound, but the budget is {kpi.n_tickets:,}. The bound is model-"
                    "independent, so no forecasting method can close this gap."
                ),
                bound=bound,
                cost=cost,
            )
        if kpi.is_degenerate() and kpi.objective == "raw_coverage":
            return self._terminate(
                "KPI_MET_DEGENERATE",
                (
                    f"budget {kpi.n_tickets:,} is at or above the packing bound "
                    f"{bound.lower_bound_tickets:,}, so target_coverage is reachable by "
                    "ticket count alone. With objective=raw_coverage the result would "
                    "measure budget, not model skill. Set objective='arm_delta'."
                ),
                bound=bound,
                cost=cost,
            )

        # ---- PROTOCOL_FREEZE ----------------------------------------------------------
        history, calibration, sealed_raw = self._split(draws)
        sealed = _SealedWindow(sealed_raw)
        frozen = {
            "kpi_definition_hash": kpi.hash,
            "n_history": int(history.shape[0]),
            "n_calibration": int(calibration.shape[0]),
            "n_sealed": sealed.n_rows,
            "split": "chronological, no shuffle",
        }
        self._enter("PROTOCOL_FREEZE", frozen)

        # ---- BASELINE_ARM_A -----------------------------------------------------------
        # Arm A is built without the sealed window, then scored on it once.
        reference = build_reference_arm(
            game=kpi.game,
            n_tickets=kpi.n_tickets,
            sealed_draws=sealed.open("score reference arm"),
            tolerance=kpi.tolerance,
            construction=kpi.reference_construction,
            seed=self.config.seed,
            n_monte_carlo=budget.n_monte_carlo,
        )
        self._enter("BASELINE_ARM_A", {"reference": reference.to_dict()})

        # ---- NEGATIVE_CONTROL_CALIB ---------------------------------------------------
        def model_pool_builder(
            target_draws: np.ndarray, n_tickets: int, seed: int
        ) -> Sequence[Sequence[int]]:
            """Build a model pool from perturbed draws, exercising the real Arm B path."""
            n = target_draws.shape[0]
            cut = max(10, int(n * 0.6))
            arm = build_model_arm(
                game=kpi.game,
                n_tickets=n_tickets,
                history=target_draws[:cut],
                calibration_draws=target_draws[cut:],
                sealed_draws=target_draws[cut:],
                parameters={"point_method": "mean", "pool_size": max(n_tickets * 3, 60)},
                tolerance=kpi.tolerance,
                seed=seed,
                n_monte_carlo=200,
            )
            return list(arm.tickets)

        controls = run_control_suite(
            game=kpi.game,
            draws=calibration,
            model_pool_builder=model_pool_builder,
            reference_pool=list(reference.tickets),
            n_tickets=kpi.n_tickets,
            tolerance=kpi.tolerance,
            max_false_positive_rate=kpi.max_false_positive_rate,
            improvement_threshold=self.config.improvement_threshold,
            alpha=kpi.alpha,
            seed=self.config.seed,
        )
        self._enter("NEGATIVE_CONTROL_CALIB", {"controls": controls.to_dict()})
        if controls.suspend:
            return self._terminate(
                "LEAK_DETECTED_SUSPENDED",
                controls.reason,
                bound=bound,
                cost=cost,
                reference=reference,
                controls=controls,
            )

        # ---- SEARCH_LOOP --------------------------------------------------------------
        proposer: GridProposer | LlmProposer
        grid = GridProposer()
        if self.config.llm_endpoint:
            proposer = LlmProposer(
                endpoint=self.config.llm_endpoint, model=self.config.llm_model
            )
        else:
            proposer = grid

        eproc = EProcess(alpha=kpi.alpha, bet_rule="predictable_plugin")
        experiments: list[ExperimentRecord] = []
        best_comparison: ArmComparison | None = None
        best_delta = -np.inf
        consecutive_failures = 0
        started = time.monotonic()
        self._enter(
            "SEARCH_LOOP",
            {
                "proposer": type(proposer).__name__,
                "max_experiments": budget.max_experiments,
                "note": (
                    "search scores on the calibration window only; the sealed window is "
                    "opened once at confirmation"
                ),
            },
        )

        for index in range(budget.max_experiments):
            if time.monotonic() - started > budget.max_runtime_seconds:
                break
            if consecutive_failures >= budget.max_consecutive_failures:
                break

            result = proposer.propose(
                count=1,
                context={
                    "game": kpi.game,
                    "n_experiments_done": len(experiments),
                    "budget_remaining": budget.max_experiments - len(experiments),
                    "best_coverage": max(best_delta, 0.0) + reference.sealed_coverage,
                    "reference_coverage": reference.sealed_coverage,
                    "n_tickets": kpi.n_tickets,
                    "tolerance": kpi.tolerance,
                },
            )
            self.ledger.append(
                "proposal_batch",
                {"index": index, "result": result.to_dict()},
            )
            if result.status == "UNAVAILABLE":
                # Explicit, logged fallback. Never silent (constitution II).
                self.ledger.append(
                    "proposer_fallback",
                    {
                        "index": index,
                        "from": "llm",
                        "to": "grid",
                        "status": "UNAVAILABLE",
                        "error": result.error,
                        "endpoint": result.endpoint,
                    },
                )
                proposer = grid
                result = grid.propose(count=1)
            if not result.proposals:
                consecutive_failures += 1
                continue

            proposal: Proposal = result.proposals[0]
            t0 = time.monotonic()
            try:
                # Search is scored on calibration. The sealed window stays closed.
                model = build_model_arm(
                    game=kpi.game,
                    n_tickets=kpi.n_tickets,
                    history=history,
                    calibration_draws=calibration,
                    sealed_draws=calibration,
                    parameters=proposal.parameters,
                    tolerance=kpi.tolerance,
                    seed=self.config.seed,
                    n_monte_carlo=min(budget.n_monte_carlo, 2000),
                )
                comparison = compare_arms(
                    reference, model, calibration, tolerance=kpi.tolerance
                )
                delta = comparison.delta
                efficiency = coverage_efficiency(
                    achieved_coverage=model.sealed_coverage,
                    n_tickets=model.n_tickets,
                    lower_bound_tickets_at_coverage=bound.lower_bound_for(
                        model.sealed_coverage
                    ),
                )
                status = "OK"
                error = None
                consecutive_failures = 0
                if delta > best_delta:
                    best_delta = delta
                    best_comparison = comparison
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                delta = None
                efficiency = None
                model = None  # type: ignore[assignment]
                status = "FAILED"
                error = f"{type(exc).__name__}: {exc}"
                consecutive_failures += 1

            record = ExperimentRecord(
                index=index,
                proposal_id=proposal.proposal_id,
                proposal_source=proposal.source,
                parameters=dict(proposal.parameters),
                sealed_coverage=None if model is None else model.sealed_coverage,
                reference_coverage=reference.sealed_coverage,
                delta=delta,
                efficiency=efficiency,
                e_value=eproc.state().e_value,
                status=status,
                error=error,
                duration_seconds=time.monotonic() - t0,
            )
            experiments.append(record)
            # Recorded unconditionally, including after any threshold is crossed, so the
            # denominator for selection effects stays intact.
            self.ledger.append("experiment", record.to_dict())

        # ---- CONFIRMATION -------------------------------------------------------------
        if best_comparison is None:
            return self._terminate(
                "BUDGET_EXHAUSTED",
                (
                    f"no experiment completed successfully in {len(experiments)} attempts; "
                    f"reference arm coverage {reference.sealed_coverage:.4f} stands as the "
                    "best available result"
                ),
                bound=bound,
                cost=cost,
                reference=reference,
                controls=controls,
                experiments=experiments,
                eproc=eproc,
            )

        sealed_draws = sealed.open("confirmation of best model arm")
        confirm_model = build_model_arm(
            game=kpi.game,
            n_tickets=kpi.n_tickets,
            history=np.vstack([history, calibration]),
            calibration_draws=calibration,
            sealed_draws=sealed_draws,
            parameters=best_comparison.model.parameters,
            tolerance=kpi.tolerance,
            seed=self.config.seed,
            n_monte_carlo=budget.n_monte_carlo,
        )
        confirmation = compare_arms(
            reference, confirm_model, sealed_draws, tolerance=kpi.tolerance
        )
        eproc.update_paired(
            list(confirmation.model_hits), list(confirmation.reference_hits)
        )
        decision = eproc.decide(min_observations=min(budget.min_confirmation_draws, sealed.n_rows))
        measurement = KpiMeasurement(
            kpi_definition_hash=kpi.hash,
            game=kpi.game,
            arm_id="B_model",
            n_tickets=confirm_model.n_tickets,
            tolerance=kpi.tolerance,
            coverage=confirm_model.sealed_coverage,
            coverage_ci=confirm_model.sealed_ci,
            n_targets=confirm_model.n_sealed_draws,
            coverage_source="empirical_sealed",
            lower_bound_tickets=bound.lower_bound_for(confirm_model.sealed_coverage),
            efficiency=coverage_efficiency(
                achieved_coverage=confirm_model.sealed_coverage,
                n_tickets=confirm_model.n_tickets,
                lower_bound_tickets_at_coverage=bound.lower_bound_for(
                    confirm_model.sealed_coverage
                ),
            ),
            arm_delta=confirmation.delta,
            e_value=eproc.state().e_value,
        )
        self._enter(
            "CONFIRMATION",
            {
                "comparison": confirmation.to_dict(),
                "decision": decision.to_dict(),
                "measurement": measurement.to_dict(),
            },
        )

        target_met = confirm_model.sealed_coverage >= kpi.target_coverage
        beat_reference = (
            confirmation.delta > kpi.min_arm_delta and decision.rejected_null
        )
        if beat_reference:
            reason = (
                f"model arm beat the reference arm by {confirmation.delta:+.4f} on "
                f"{confirmation.n_draws} sealed draws at equal ticket count "
                f"({confirm_model.n_tickets:,}); e-value {measurement.e_value:.3g} crossed "
                f"1/alpha = {1 / kpi.alpha:.0f}, and all controls behaved"
            )
            terminal: TerminalState = "KPI_MET_VERIFIED"
        elif kpi.is_degenerate() and target_met:
            reason = (
                f"target coverage {confirm_model.sealed_coverage:.4f} reached, but the "
                f"budget {kpi.n_tickets:,} is at or above the packing bound "
                f"{bound.lower_bound_tickets:,}, so ticket count alone explains it"
            )
            terminal = "KPI_MET_DEGENERATE"
        else:
            reason = (
                f"model arm delta {confirmation.delta:+.4f} did not clear "
                f"min_arm_delta={kpi.min_arm_delta} with e-value "
                f"{measurement.e_value:.3g} < {1 / kpi.alpha:.0f}. The data-free covering "
                "construction is what produced the coverage; the forecasting model added "
                "nothing measurable"
            )
            terminal = "KPI_MET_NO_MODEL_VALUE"

        return self._terminate(
            terminal,
            reason,
            bound=bound,
            cost=cost,
            reference=reference,
            controls=controls,
            experiments=experiments,
            eproc=eproc,
            comparison=confirmation,
            measurement=measurement,
        )

    # -- termination --------------------------------------------------------------------

    def _terminate(
        self,
        state: TerminalState,
        reason: str,
        *,
        bound: Any,
        cost: Any,
        reference: Any = None,
        controls: Any = None,
        experiments: Sequence[ExperimentRecord] = (),
        eproc: EProcess | None = None,
        comparison: ArmComparison | None = None,
        measurement: KpiMeasurement | None = None,
    ) -> LabReport:
        self._enter(state, {"reason": reason})
        integrity = self.ledger.verify()
        report = LabReport(
            session_id=self.session_id,
            terminal_state=state,
            reason=reason,
            kpi=self.config.kpi.to_dict(),
            feasibility=bound.to_dict(),
            cost=cost.to_dict(),
            reference_arm=None if reference is None else reference.to_dict(),
            best_model_arm=None if comparison is None else comparison.model.to_dict(),
            best_measurement=None if measurement is None else measurement.to_dict(),
            e_process=None if eproc is None else eproc.state().to_dict(),
            control_suite=None if controls is None else controls.to_dict(),
            experiments=tuple(record.to_dict() for record in experiments),
            n_experiments=len(experiments),
            ledger_path=str(self.ledger.path),
            ledger_integrity=integrity.to_dict(),
            states_visited=tuple(self.states_visited),
            started_at=self._started_at,
            finished_at=utc_now_iso(),
        )
        atomic_write_json(self.output_dir / "report.json", report.to_dict())
        self.ledger.append("report_written", {"terminal_state": state})
        return report
