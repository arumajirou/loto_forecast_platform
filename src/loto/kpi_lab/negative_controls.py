"""Negative and positive controls, run inside every search iteration.

Why inside the loop
-------------------
A control suite run once at the end answers "does the final winner survive?". It cannot
answer "is this search procedure manufacturing winners?", because by the time it runs, the
selection has already happened. Leakage and selection bias accumulate *during* search, so
the controls have to accumulate alongside them.

The suite mixes two kinds of check, and both are needed:

negative controls
    Inputs with the signal destroyed. A search procedure that still reports improvement on
    permuted labels, shifted features, or synthetic uniform draws is measuring its own
    optimism. Expected verdict: no improvement.
positive control
    Input with signal deliberately injected. A suite that never fires has no demonstrated
    power, so a clean sweep of negatives would be meaningless. Expected verdict:
    improvement detected.

The false-positive rate across negative controls is compared against
``max_false_positive_rate``. Exceeding it suspends the lab rather than downgrading the
threshold, because a threshold that moves when it binds is not a threshold.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from loto.combinatorics.estimate import per_draw_hits, uniform_outcomes
from loto.game.geometry import geometry_for
from loto.kpi_lab.stopping import mcnemar_e_value

__all__ = [
    "ControlKind",
    "ControlOutcome",
    "ControlResult",
    "ControlSuiteReport",
    "NEGATIVE_CONTROLS",
    "POSITIVE_CONTROLS",
    "run_control_suite",
    "permute_draws",
    "time_shift_draws",
    "inject_future_leak",
    "synthetic_uniform_draws",
]

ControlKind = Literal["negative", "positive"]
ControlOutcome = Literal["PASS", "FAIL", "INCONCLUSIVE"]
_SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------------------
# perturbations
# --------------------------------------------------------------------------------------


def permute_draws(draws: np.ndarray, *, seed: int = 42) -> np.ndarray:
    """Shuffle draw order, destroying any temporal relationship to the features."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(draws, dtype=np.int64).copy()
    rng.shuffle(arr, axis=0)
    return arr


def time_shift_draws(draws: np.ndarray, *, shift: int = 1) -> np.ndarray:
    """Shift the target series so each prediction is aligned to the wrong draw."""
    arr = np.asarray(draws, dtype=np.int64)
    if shift == 0 or arr.shape[0] <= abs(shift):
        return arr.copy()
    return np.roll(arr, shift, axis=0)


def inject_future_leak(
    draws: np.ndarray, *, fraction: float = 1.0, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Positive control: a pool containing the scored answers themselves.

    ``fraction`` defaults to 1.0 so the injected pool covers every scored draw and the
    delta against the reference arm is unambiguous. A lower fraction caps coverage at that
    fraction, which can sit *below* a good reference arm's coverage and make the control
    silently fail to fire -- turning the power check into a false reassurance.

    A detector that does not fire here has no demonstrated power, so this control is what
    licenses any interpretation of the negative controls passing.
    """
    arr = np.asarray(draws, dtype=np.int64)
    if fraction >= 1.0:
        return arr, arr.copy()
    rng = np.random.default_rng(seed)
    n_leak = max(1, int(arr.shape[0] * fraction))
    idx = rng.choice(arr.shape[0], size=n_leak, replace=False)
    return arr, arr[idx].copy()


def synthetic_uniform_draws(game: str, *, n_draws: int, seed: int = 42) -> np.ndarray:
    """Draws generated from the exact uniform law -- guaranteed to contain no signal."""
    return uniform_outcomes(game, n_samples=n_draws, seed=seed)


def shuffle_pool_values(pool: Sequence[Sequence[int]], *, game: str, seed: int = 42):
    """Replace the pool with random legal tickets of the same count."""
    from loto.combinatorics.designs import random_legal_pool

    tickets, _ = random_legal_pool(game, n_tickets=len(pool), seed=seed)
    return tickets


def constant_pool(game: str, *, n_tickets: int) -> list[tuple[int, ...]]:
    """A single ticket repeated -- the degenerate predictor a coverage metric must not reward."""
    geometry = geometry_for(game)
    if geometry.family == "select":
        base = tuple(range(geometry.value_min, geometry.value_min + geometry.positions))
    else:
        mid = (geometry.value_min + geometry.value_max) // 2
        base = tuple(mid for _ in range(geometry.positions))
    return [base] * max(1, n_tickets)


# --------------------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlResult:
    """One control, its expectation, and whether reality matched."""

    name: str
    kind: ControlKind
    expectation: str
    model_coverage: float
    reference_coverage: float
    delta: float
    threshold: float
    e_value: float
    e_threshold: float
    n_discordant: int
    outcome: ControlOutcome
    detail: str
    n_draws: int
    n_tickets: int
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ControlSuiteReport:
    """Aggregate verdict. ``suspend`` is the only field the state machine acts on."""

    results: tuple[ControlResult, ...]
    n_negative: int
    n_negative_failed: int
    false_positive_rate: float
    max_false_positive_rate: float
    positive_controls_fired: int
    n_positive: int
    suspend: bool
    reason: str
    schema_version: str = _SCHEMA_VERSION

    @property
    def has_demonstrated_power(self) -> bool:
        return self.n_positive > 0 and self.positive_controls_fired == self.n_positive

    def to_dict(self) -> dict[str, object]:
        return {
            "results": [r.to_dict() for r in self.results],
            "n_negative": self.n_negative,
            "n_negative_failed": self.n_negative_failed,
            "false_positive_rate": self.false_positive_rate,
            "max_false_positive_rate": self.max_false_positive_rate,
            "positive_controls_fired": self.positive_controls_fired,
            "n_positive": self.n_positive,
            "has_demonstrated_power": self.has_demonstrated_power,
            "suspend": self.suspend,
            "reason": self.reason,
            "schema_version": self.schema_version,
        }


NEGATIVE_CONTROLS: tuple[str, ...] = (
    "label_permutation",
    "time_shift",
    "synthetic_uniform",
    "shuffled_pool",
    "constant_pool",
)
POSITIVE_CONTROLS: tuple[str, ...] = ("future_injection",)


# --------------------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------------------

#: A pool builder receives ``(build_draws, n_tickets, seed)`` and returns a ticket pool.
#: The lab passes the *model* arm builder here so the controls exercise the real path.
#:
#: The builder must never receive the rows the control will score on. :func:`run_control_suite`
#: enforces that by splitting the perturbed draws itself and handing over only the prefix --
#: an earlier revision passed the full array and every negative control fired, because the
#: harness was leaking rather than the model. A control suite that leaks measures itself.
PoolBuilder = Callable[[np.ndarray, int, int], Sequence[Sequence[int]]]


def _coverage(draws: np.ndarray, pool: Sequence[Sequence[int]], tolerance: int) -> float:
    if len(pool) == 0 or draws.shape[0] == 0:
        return 0.0
    return float(per_draw_hits(draws, pool, tolerance=tolerance).mean())


def run_control_suite(
    *,
    game: str,
    draws: np.ndarray,
    model_pool_builder: PoolBuilder,
    reference_pool: Sequence[Sequence[int]],
    n_tickets: int,
    tolerance: int = 1,
    max_false_positive_rate: float = 0.05,
    improvement_threshold: float = 0.02,
    alpha: float = 0.01,
    build_fraction: float = 0.6,
    seed: int = 42,
) -> ControlSuiteReport:
    """Run the whole suite and return an aggregate verdict.

    Detection requires both statistical evidence (paired e-value >= ``1/alpha``) and a
    minimum effect (``delta >= improvement_threshold``). The e-value is what bounds the
    null firing rate at ``alpha`` regardless of how many draws the window holds; a fixed
    delta alone cannot, because its firing rate depends on the sampling noise of the window.
    On a negative control any detection is a false positive.
    """
    draws = np.asarray(draws, dtype=np.int64)
    n_rows = int(draws.shape[0])
    if n_rows < 20:
        raise ValueError(f"control suite needs at least 20 draws, got {n_rows}")
    cut = max(10, int(n_rows * build_fraction))
    if cut >= n_rows - 4:
        cut = n_rows - 5
    results: list[ControlResult] = []

    def build_and_score(
        name: str,
        expectation: str,
        perturbed: np.ndarray,
        detail: str,
        seed_offset: int = 0,
    ) -> None:
        """Build on the prefix, score on the disjoint suffix. No overlap, ever."""
        build_rows, score_rows = perturbed[:cut], perturbed[cut:]
        pool = model_pool_builder(build_rows, n_tickets, seed + seed_offset)
        record(name, "negative", expectation, score_rows, pool, reference_pool, detail)

    def record(
        name: str,
        kind: ControlKind,
        expectation: str,
        target_draws: np.ndarray,
        pool: Sequence[Sequence[int]],
        reference_for_pairing: Sequence[Sequence[int]],
        detail: str,
    ) -> None:
        """Decide "improvement detected" statistically, not by a bare delta.

        An earlier revision compared point-estimate deltas against a fixed 0.02. On a scored
        window of ~50 draws the sampling standard deviation of a coverage estimate is about
        0.07, so that rule fired on roughly half the negative controls by chance: the suite's
        own false-positive rate was near 50%, not the 5% it claimed to enforce. Comparing a
        count of such firings against ``max_false_positive_rate`` was therefore meaningless.

        Detection now requires BOTH a paired e-value crossing ``1/alpha`` -- which bounds the
        null firing probability at ``alpha`` by Ville's inequality, whatever the window size --
        and a minimum effect size. Requiring both keeps the suite from flagging effects that
        are significant but too small to matter.
        """
        model_hits = (
            per_draw_hits(target_draws, pool, tolerance=tolerance)
            if len(pool)
            else np.zeros(target_draws.shape[0], dtype=bool)
        )
        ref_hits = (
            per_draw_hits(target_draws, reference_for_pairing, tolerance=tolerance)
            if len(reference_for_pairing)
            else np.zeros(target_draws.shape[0], dtype=bool)
        )
        model_cov = float(model_hits.mean()) if model_hits.size else 0.0
        ref_cov = float(ref_hits.mean()) if ref_hits.size else 0.0
        delta = model_cov - ref_cov
        state = mcnemar_e_value(list(model_hits), list(ref_hits), alpha=alpha)
        e_threshold = 1.0 / alpha
        detected = state.e_value >= e_threshold and delta >= improvement_threshold
        if kind == "negative":
            outcome: ControlOutcome = "FAIL" if detected else "PASS"
        else:
            outcome = "PASS" if detected else "FAIL"
        results.append(
            ControlResult(
                name=name,
                kind=kind,
                expectation=expectation,
                model_coverage=model_cov,
                reference_coverage=ref_cov,
                delta=delta,
                threshold=improvement_threshold,
                e_value=state.e_value,
                e_threshold=e_threshold,
                n_discordant=state.n_observations,
                outcome=outcome,
                detail=detail,
                n_draws=int(target_draws.shape[0]),
                n_tickets=len(pool),
            )
        )

    # 1. label permutation
    build_and_score(
        "label_permutation",
        "no improvement over reference once draw order is destroyed",
        permute_draws(draws, seed=seed),
        "draws shuffled; any remaining edge is optimism, not signal",
    )

    # 2. time shift
    build_and_score(
        "time_shift",
        "no improvement when targets are misaligned by one draw",
        time_shift_draws(draws, shift=1),
        "targets rolled by one position relative to history",
        seed_offset=1,
    )

    # 3. synthetic uniform
    build_and_score(
        "synthetic_uniform",
        "no improvement on draws generated from the exact uniform law",
        synthetic_uniform_draws(game, n_draws=n_rows, seed=seed + 7),
        "ground truth contains no exploitable structure by construction",
        seed_offset=2,
    )

    # 4. shuffled pool
    record(
        "shuffled_pool",
        "negative",
        "a random legal pool of equal size must not beat the reference",
        draws[cut:],
        shuffle_pool_values(reference_pool, game=game, seed=seed + 11),
        reference_pool,
        "pool design removed, ticket count preserved",
    )

    # 5. constant pool
    record(
        "constant_pool",
        "negative",
        "a repeated single ticket must not score as a large pool",
        draws[cut:],
        constant_pool(game, n_tickets=n_tickets),
        reference_pool,
        "degenerate predictor; catches metrics that reward duplicate tickets",
    )

    # 6. positive control: future injection
    leak_draws, leak_pool = inject_future_leak(draws[cut:], fraction=1.0, seed=seed + 13)
    record(
        "future_injection",
        "positive",
        "detector MUST fire when the answers are placed in the pool",
        leak_draws,
        list(leak_pool),
        reference_pool,
        "every scored draw inserted into the pool verbatim; coverage is 1.0 by construction",
    )

    negatives = [r for r in results if r.kind == "negative"]
    positives = [r for r in results if r.kind == "positive"]
    failed = [r for r in negatives if r.outcome == "FAIL"]
    fp_rate = len(failed) / len(negatives) if negatives else 0.0
    fired = sum(1 for r in positives if r.outcome == "PASS")

    suspend = False
    reasons: list[str] = []
    if fp_rate > max_false_positive_rate:
        suspend = True
        reasons.append(
            f"false-positive rate {fp_rate:.3f} exceeds {max_false_positive_rate:.3f} "
            f"(failed: {', '.join(r.name for r in failed)})"
        )
    if positives and fired < len(positives):
        suspend = True
        reasons.append(
            "positive control did not fire; the suite has no demonstrated power, so "
            "passing negatives carry no information"
        )
    return ControlSuiteReport(
        results=tuple(results),
        n_negative=len(negatives),
        n_negative_failed=len(failed),
        false_positive_rate=fp_rate,
        max_false_positive_rate=max_false_positive_rate,
        positive_controls_fired=fired,
        n_positive=len(positives),
        suspend=suspend,
        reason="; ".join(reasons) if reasons else "all controls behaved as expected",
    )
