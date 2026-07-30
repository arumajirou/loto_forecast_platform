"""Anytime-valid stopping rules for the KPI lab.

The rule this replaces
----------------------
``SearchBudget.stop_when_target_met = True`` halts at the first experiment whose
validation score clears the threshold. Across 500 experiments that is a maximum-selection
procedure: it reports the best of many draws as if it were a single measurement, so the
nominal threshold no longer controls the error rate. The reported winner is the one that
got lucky, which is precisely why such winners collapse out of sample.

What replaces it
----------------
A betting e-process. For each sealed draw we observe a paired indicator

    Z_i = 1{model arm covers draw i} - 1{reference arm covers draw i}   in {-1, 0, +1}

Under the null "the model arm is no better than the reference arm" we have ``E[Z_i] <= 0``.
The wealth process

    E_n = prod_{i<=n} (1 + lambda_i * Z_i),    lambda_i predictable, 0 < lambda_i <= 1/2

is a non-negative supermartingale under that null, so by Ville's inequality

    P(exists n : E_n >= 1/alpha) <= alpha.

The threshold can therefore be checked after **every** draw, continuously, without any
alpha penalty, and the experiment may be stopped the moment it is crossed. Optional
stopping is legitimate here in a way it is not for a fixed-sample p-value.

``lambda_i`` is chosen from strictly past data only (a predictable plug-in), which keeps
the supermartingale property intact. Peeking at ``Z_i`` to choose ``lambda_i`` would
destroy validity, so :class:`EProcess` computes the bet before ingesting the observation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

__all__ = [
    "EProcess",
    "EProcessState",
    "StoppingDecision",
    "mcnemar_e_value",
    "paired_e_process",
]

BetRule = Literal["fixed", "predictable_plugin"]
_SCHEMA_VERSION = "1.0.0"
_MAX_LAMBDA = 0.5


@dataclass(frozen=True)
class EProcessState:
    """Serialisable snapshot, so a lab run can be interrupted and resumed exactly."""

    log_wealth: float
    n_observations: int
    n_positive: int
    n_negative: int
    n_ties: int
    lambda_next: float
    alpha: float
    bet_rule: BetRule
    max_log_wealth: float
    crossed_at: int | None = None
    schema_version: str = _SCHEMA_VERSION

    @property
    def e_value(self) -> float:
        return math.exp(min(self.log_wealth, 700.0))

    @property
    def max_e_value(self) -> float:
        return math.exp(min(self.max_log_wealth, 700.0))

    @property
    def threshold(self) -> float:
        return 1.0 / self.alpha

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["e_value"] = self.e_value
        payload["max_e_value"] = self.max_e_value
        payload["threshold"] = self.threshold
        return payload


@dataclass(frozen=True)
class StoppingDecision:
    """Why the lab stopped, or why it has not."""

    stop: bool
    reason: str
    e_value: float
    threshold: float
    n_observations: int
    rejected_null: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EProcess:
    """Betting supermartingale for a paired one-sided comparison against a reference arm.

    Null hypothesis: ``E[Z] <= 0``, i.e. the model arm is not better. Rejecting the null
    is the *only* way this lab is permitted to declare a model-driven win.
    """

    def __init__(
        self,
        *,
        alpha: float = 0.01,
        bet_rule: BetRule = "predictable_plugin",
        fixed_lambda: float = 0.1,
        lambda_cap: float = _MAX_LAMBDA,
    ) -> None:
        if not 0 < alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        if not 0 < lambda_cap <= _MAX_LAMBDA:
            raise ValueError(f"lambda_cap must be in (0, {_MAX_LAMBDA}]")
        if not 0 < fixed_lambda <= lambda_cap:
            raise ValueError("fixed_lambda must be in (0, lambda_cap]")
        self.alpha = alpha
        self.bet_rule = bet_rule
        self.fixed_lambda = fixed_lambda
        self.lambda_cap = lambda_cap
        self._log_wealth = 0.0
        self._max_log_wealth = 0.0
        self._n = 0
        self._pos = 0
        self._neg = 0
        self._tie = 0
        self._crossed_at: int | None = None

    # -- bets ---------------------------------------------------------------------------

    def _next_lambda(self) -> float:
        """Bet size from strictly past observations. Never inspects the incoming value."""
        if self.bet_rule == "fixed" or self._n == 0:
            return min(self.fixed_lambda, self.lambda_cap)
        # plug-in: scale the bet with the observed edge so far, damped by sample size
        edge = (self._pos - self._neg) / self._n
        if edge <= 0:
            return min(self.fixed_lambda * 0.5, self.lambda_cap)
        damped = edge * self._n / (self._n + 10.0)
        return float(min(max(damped, 1e-4), self.lambda_cap))

    # -- updates ------------------------------------------------------------------------

    def update(self, z: int | float) -> EProcessState:
        """Ingest one paired observation ``z in [-1, 1]`` and return the new state."""
        if not -1.0 - 1e-12 <= float(z) <= 1.0 + 1e-12:
            raise ValueError("z must lie in [-1, 1] for the bet to stay non-negative")
        lam = self._next_lambda()
        factor = 1.0 + lam * float(z)
        if factor <= 0.0:
            # unreachable while lambda_cap <= 0.5 and |z| <= 1, but guard rather than
            # silently produce -inf wealth
            raise ValueError(f"non-positive betting factor {factor!r}")
        self._log_wealth += math.log(factor)
        self._n += 1
        if z > 0:
            self._pos += 1
        elif z < 0:
            self._neg += 1
        else:
            self._tie += 1
        if self._log_wealth > self._max_log_wealth:
            self._max_log_wealth = self._log_wealth
        if self._crossed_at is None and self._log_wealth >= math.log(1.0 / self.alpha):
            self._crossed_at = self._n
        return self.state()

    def update_many(self, values: Iterable[int | float]) -> EProcessState:
        state = self.state()
        for value in values:
            state = self.update(value)
        return state

    def update_paired(
        self, model_hits: Sequence[bool], reference_hits: Sequence[bool]
    ) -> EProcessState:
        """Ingest paired per-draw coverage indicators, in draw order."""
        if len(model_hits) != len(reference_hits):
            raise ValueError("model_hits and reference_hits must have equal length")
        state = self.state()
        for m, r in zip(model_hits, reference_hits, strict=True):
            state = self.update(int(bool(m)) - int(bool(r)))
        return state

    # -- inspection ---------------------------------------------------------------------

    def state(self) -> EProcessState:
        return EProcessState(
            log_wealth=self._log_wealth,
            n_observations=self._n,
            n_positive=self._pos,
            n_negative=self._neg,
            n_ties=self._tie,
            lambda_next=self._next_lambda(),
            alpha=self.alpha,
            bet_rule=self.bet_rule,
            max_log_wealth=self._max_log_wealth,
            crossed_at=self._crossed_at,
        )

    def decide(self, *, min_observations: int = 30) -> StoppingDecision:
        """Anytime-valid decision. Safe to call after every single observation."""
        state = self.state()
        threshold = 1.0 / self.alpha
        if state.n_observations < min_observations:
            return StoppingDecision(
                stop=False,
                reason=f"insufficient observations ({state.n_observations}<{min_observations})",
                e_value=state.e_value,
                threshold=threshold,
                n_observations=state.n_observations,
                rejected_null=False,
            )
        if state.e_value >= threshold:
            return StoppingDecision(
                stop=True,
                reason="e_value crossed 1/alpha; null rejected under Ville's inequality",
                e_value=state.e_value,
                threshold=threshold,
                n_observations=state.n_observations,
                rejected_null=True,
            )
        return StoppingDecision(
            stop=False,
            reason="e_value below threshold; no evidence against the null yet",
            e_value=state.e_value,
            threshold=threshold,
            n_observations=state.n_observations,
            rejected_null=False,
        )

    @classmethod
    def restore(cls, state: EProcessState | dict[str, object]) -> EProcess:
        """Rebuild from a serialised state so resume produces identical continuation."""
        data = state.to_dict() if isinstance(state, EProcessState) else dict(state)
        obj = cls(
            alpha=float(data["alpha"]),
            bet_rule=str(data["bet_rule"]),  # type: ignore[arg-type]
        )
        obj._log_wealth = float(data["log_wealth"])
        obj._max_log_wealth = float(data.get("max_log_wealth", data["log_wealth"]))
        obj._n = int(data["n_observations"])
        obj._pos = int(data["n_positive"])
        obj._neg = int(data["n_negative"])
        obj._tie = int(data["n_ties"])
        crossed = data.get("crossed_at")
        obj._crossed_at = None if crossed is None else int(crossed)
        return obj


def mcnemar_e_value(
    model_hits: Sequence[bool],
    reference_hits: Sequence[bool],
    *,
    alpha: float = 0.01,
    bet_rule: BetRule = "predictable_plugin",
) -> EProcessState:
    """E-value over discordant pairs only -- the e-process analogue of McNemar's test.

    Ties carry no information about which arm is better, so discarding them concentrates
    the bet. Validity is unaffected because the discordant subsequence is still adapted to
    the draw order.

    The bet rule is adaptive by default. A fixed ``lambda = 0.1`` is badly under-powered:
    on 29 discordant pairs all favouring one arm it yields ``1.1**29 ~ 17``, short of the
    ``1/alpha = 100`` threshold, so an unmistakable effect fails to register. Because
    ``lambda`` is computed from strictly past observations it stays predictable, and the
    supermartingale property -- hence validity -- is preserved.
    """
    if len(model_hits) != len(reference_hits):
        raise ValueError("model_hits and reference_hits must have equal length")
    e = EProcess(alpha=alpha, bet_rule=bet_rule)
    for m, r in zip(model_hits, reference_hits, strict=True):
        z = int(bool(m)) - int(bool(r))
        if z != 0:
            e.update(z)
    return e.state()


def paired_e_process(
    model_hits: Sequence[bool],
    reference_hits: Sequence[bool],
    *,
    alpha: float = 0.01,
    bet_rule: BetRule = "predictable_plugin",
    min_observations: int = 30,
) -> tuple[EProcessState, StoppingDecision]:
    """Convenience wrapper: run the full paired sequence and return state plus decision."""
    e = EProcess(alpha=alpha, bet_rule=bet_rule)
    e.update_paired(model_hits, reference_hits)
    return e.state(), e.decide(min_observations=min_observations)
