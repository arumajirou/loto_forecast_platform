"""Strict result contracts for exploratory statistical analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RepresentationKind = Literal[
    "unordered_draw_feature",
    "sorted_position",
    "draw_aggregate",
    "external_feature",
    "generic_numeric_series",
]


class AssociationResult(BaseModel):
    """One bivariate association estimate.

    ``causal_claim_eligible`` is intentionally fixed to False. Correlation can support
    hypothesis generation but can never, by itself, satisfy the causal-identification gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["pearson", "spearman"]
    statistic: float = Field(ge=-1.0, le=1.0)
    p_value: float = Field(ge=0.0, le=1.0)
    n: int = Field(ge=3)
    representation: RepresentationKind
    null_hypothesis: str = "zero association"
    causal_claim_eligible: Literal[False] = False


class SerialDependenceResult(BaseModel):
    """Ljung-Box portmanteau test result for a declared lag horizon."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["ljung_box"] = "ljung_box"
    lags: int = Field(ge=1)
    statistic: float = Field(ge=0.0)
    p_value: float = Field(ge=0.0, le=1.0)
    autocorrelations: tuple[float, ...]
    n: int = Field(ge=4)
    null_hypothesis: str = "no serial correlation through the declared lag horizon"
    causal_claim_eligible: Literal[False] = False


class TrendResult(BaseModel):
    """Linear time-index trend fit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["linear_time_trend"] = "linear_time_trend"
    slope: float
    intercept: float
    r_value: float = Field(ge=-1.0, le=1.0)
    p_value: float = Field(ge=0.0, le=1.0)
    stderr: float = Field(ge=0.0)
    n: int = Field(ge=3)
    causal_claim_eligible: Literal[False] = False


class ChangePointResult(BaseModel):
    """Maximum mean-shift scan with a permutation-calibrated family-wise p-value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["max_mean_shift_permutation"] = "max_mean_shift_permutation"
    split_index: int = Field(ge=1)
    left_mean: float
    right_mean: float
    mean_shift: float
    absolute_mean_shift: float = Field(ge=0.0)
    standardized_effect: float | None
    permutation_p_value: float = Field(ge=0.0, le=1.0)
    repetitions: int = Field(ge=1)
    seed: int
    min_segment: int = Field(ge=2)
    n: int = Field(ge=4)
    causal_claim_eligible: Literal[False] = False


class AdjustedHypothesis(BaseModel):
    """One hypothesis after a declared family-level multiplicity correction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str = Field(min_length=1)
    method: Literal["holm", "benjamini_hochberg"]
    alpha: float = Field(gt=0.0, lt=1.0)
    raw_p_value: float = Field(ge=0.0, le=1.0)
    adjusted_p_value: float = Field(ge=0.0, le=1.0)
    rejected: bool
