from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class ProbabilityQuality:
    count: int
    finite: bool
    minimum: float
    maximum: float
    mean: float
    standard_deviation: float
    unique_count: int
    expected_positive_mass: float
    near_constant: bool
    valid_probability_range: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_candidate_probabilities(
    probabilities: np.ndarray,
    *,
    expected_count: int = 37,
    minimum_standard_deviation: float = 1e-8,
) -> ProbabilityQuality:
    values = np.asarray(probabilities, dtype=float).reshape(-1)

    finite = bool(np.isfinite(values).all())
    minimum = float(np.min(values)) if values.size else float("nan")
    maximum = float(np.max(values)) if values.size else float("nan")
    mean = float(np.mean(values)) if values.size else float("nan")
    std = float(np.std(values)) if values.size else float("nan")
    unique_count = int(np.unique(values).size) if values.size else 0

    return ProbabilityQuality(
        count=int(values.size),
        finite=finite,
        minimum=minimum,
        maximum=maximum,
        mean=mean,
        standard_deviation=std,
        unique_count=unique_count,
        expected_positive_mass=float(np.sum(values)),
        near_constant=bool(
            finite and values.size == expected_count and std <= minimum_standard_deviation
        ),
        valid_probability_range=bool(
            finite and values.size == expected_count and minimum >= 0.0 and maximum <= 1.0
        ),
    )


def require_candidate_probability_quality(
    probabilities: np.ndarray,
    *,
    model_id: str,
    expected_count: int = 37,
    minimum_standard_deviation: float = 1e-8,
) -> ProbabilityQuality:
    report = assess_candidate_probabilities(
        probabilities,
        expected_count=expected_count,
        minimum_standard_deviation=minimum_standard_deviation,
    )

    if report.count != expected_count:
        raise RuntimeError(
            f"{model_id}: expected {expected_count} probabilities, got {report.count}"
        )
    if not report.finite:
        raise RuntimeError(f"{model_id}: non-finite probabilities")
    if not report.valid_probability_range:
        raise RuntimeError(f"{model_id}: probabilities outside [0, 1]")
    if report.near_constant:
        raise RuntimeError(
            f"{model_id}: near-constant candidate probabilities "
            f"(std={report.standard_deviation:.3e}, "
            f"mean={report.mean:.3e}); this commonly indicates target "
            "leakage during fit followed by a missing target at inference"
        )

    return report
