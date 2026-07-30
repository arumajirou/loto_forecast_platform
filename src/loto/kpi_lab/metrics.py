"""Prometheus metrics for the KPI lab.

Cardinality discipline: labels are restricted to ``game``, ``arm``, ``construction`` and the
terminal-state enum -- all small, closed sets. Session, experiment and proposal identifiers
are high-cardinality and belong in the ledger and the report, not in label values, because a
Prometheus series per experiment would grow without bound.

``prometheus_client`` is a hard dependency of the project, but this module still degrades to
no-ops if the registry cannot be created, and says so, rather than raising at import time and
taking down a lab run over telemetry.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "METRIC_NAMES",
    "LabMetrics",
    "metrics_available",
]

METRIC_NAMES: tuple[str, ...] = (
    "loto_lab_experiments_total",
    "loto_lab_coverage",
    "loto_lab_coverage_efficiency",
    "loto_lab_tickets_count",
    "loto_lab_lower_bound_tickets",
    "loto_lab_arm_delta",
    "loto_lab_e_value",
    "loto_lab_negative_control_fp_rate",
    "loto_lab_terminal_state",
    "loto_lab_protocol_violation_total",
    "loto_lab_ledger_valid",
)

try:  # pragma: no cover - exercised only by dependency state
    from prometheus_client import CollectorRegistry, Counter, Gauge

    _AVAILABLE = True
    _IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover
    _AVAILABLE = False
    _IMPORT_ERROR = str(exc)


def metrics_available() -> tuple[bool, str | None]:
    """Whether Prometheus metrics can be emitted, and the exact error if not."""
    return _AVAILABLE, _IMPORT_ERROR


class LabMetrics:
    """Metric holder for one lab process.

    Uses its own ``CollectorRegistry`` so repeated construction inside tests cannot collide
    with the global default registry.
    """

    def __init__(self, registry: Any | None = None) -> None:
        self.enabled = _AVAILABLE
        self.import_error = _IMPORT_ERROR
        if not self.enabled:
            self.registry = None
            return
        self.registry = registry if registry is not None else CollectorRegistry()
        self.experiments_total = Counter(
            "loto_lab_experiments_total",
            "Search-loop experiments executed, including failures.",
            ["game", "status"],
            registry=self.registry,
        )
        self.coverage = Gauge(
            "loto_lab_coverage",
            "Coverage of an arm on its scoring window.",
            ["game", "arm", "source"],
            registry=self.registry,
        )
        self.efficiency = Gauge(
            "loto_lab_coverage_efficiency",
            "KPI-1: required tickets at achieved coverage divided by tickets used. 1.0 is "
            "the packing bound; above 1.0 is impossible.",
            ["game", "arm"],
            registry=self.registry,
        )
        self.tickets = Gauge(
            "loto_lab_tickets_count",
            "Fixed ticket budget for the arm.",
            ["game", "arm"],
            registry=self.registry,
        )
        self.lower_bound = Gauge(
            "loto_lab_lower_bound_tickets",
            "Model-independent packing bound on tickets for the target coverage.",
            ["game"],
            registry=self.registry,
        )
        self.arm_delta = Gauge(
            "loto_lab_arm_delta",
            "KPI-2: model arm coverage minus reference arm coverage at equal ticket count.",
            ["game"],
            registry=self.registry,
        )
        self.e_value = Gauge(
            "loto_lab_e_value",
            "Anytime-valid e-value against the null that the model arm is no better.",
            ["game"],
            registry=self.registry,
        )
        self.fp_rate = Gauge(
            "loto_lab_negative_control_fp_rate",
            "Observed false-positive rate across negative controls.",
            ["game"],
            registry=self.registry,
        )
        self.terminal_state = Gauge(
            "loto_lab_terminal_state",
            "One-hot indicator of the terminal state reached.",
            ["game", "state"],
            registry=self.registry,
        )
        self.protocol_violations = Counter(
            "loto_lab_protocol_violation_total",
            "Protocol hash mismatches and sealed-window access attempts.",
            ["game", "kind"],
            registry=self.registry,
        )
        self.ledger_valid = Gauge(
            "loto_lab_ledger_valid",
            "1 when the experiment ledger hash chain verifies, 0 otherwise.",
            ["game"],
            registry=self.registry,
        )

    # -- recording ----------------------------------------------------------------------

    def observe_experiment(self, *, game: str, status: str) -> None:
        if self.enabled:
            self.experiments_total.labels(game=game, status=status).inc()

    def observe_arm(
        self,
        *,
        game: str,
        arm: str,
        sealed_coverage: float,
        monte_carlo_coverage: float,
        efficiency: float | None,
        n_tickets: int,
    ) -> None:
        if not self.enabled:
            return
        self.coverage.labels(game=game, arm=arm, source="sealed").set(sealed_coverage)
        self.coverage.labels(game=game, arm=arm, source="monte_carlo").set(
            monte_carlo_coverage
        )
        self.tickets.labels(game=game, arm=arm).set(n_tickets)
        if efficiency is not None:
            self.efficiency.labels(game=game, arm=arm).set(efficiency)

    def observe_report(self, report: Any) -> None:
        """Record everything a finished :class:`~loto.kpi_lab.state_machine.LabReport` carries."""
        if not self.enabled:
            return
        payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        game = str(payload.get("kpi", {}).get("game", "unknown"))
        feasibility = payload.get("feasibility") or {}
        if "lower_bound_tickets" in feasibility:
            self.lower_bound.labels(game=game).set(feasibility["lower_bound_tickets"])
        measurement = payload.get("best_measurement") or {}
        if measurement.get("arm_delta") is not None:
            self.arm_delta.labels(game=game).set(measurement["arm_delta"])
        if measurement.get("e_value") is not None:
            self.e_value.labels(game=game).set(measurement["e_value"])
        controls = payload.get("control_suite") or {}
        if "false_positive_rate" in controls:
            self.fp_rate.labels(game=game).set(controls["false_positive_rate"])
        integrity = payload.get("ledger_integrity") or {}
        self.ledger_valid.labels(game=game).set(1 if integrity.get("valid") else 0)
        state = str(payload.get("terminal_state", "unknown"))
        from loto.kpi_lab.state_machine import TERMINAL_STATES

        for candidate in TERMINAL_STATES:
            self.terminal_state.labels(game=game, state=candidate).set(
                1 if candidate == state else 0
            )

    def render(self) -> bytes:
        """Expose in Prometheus text format, for scraping or for an evidence artifact."""
        if not self.enabled or self.registry is None:
            return b""
        from prometheus_client import generate_latest

        return generate_latest(self.registry)
