from __future__ import annotations

import numpy as np

from loto.probabilistic.contracts import DiagnosticReport


def diagnose_probabilities(
    probabilities: np.ndarray,
    *,
    backend: str,
    inference_profile_id: str | None,
    point_predictions: list[int] | None = None,
) -> DiagnosticReport:
    probs = np.asarray(probabilities, dtype=float)
    finite = bool(np.isfinite(probs).all())
    simplex = bool(
        finite
        and np.all(probs >= -1e-12)
        and np.all(probs <= 1.0 + 1e-12)
        and np.allclose(probs.sum(axis=-1), 1.0, atol=1e-7)
    )
    warnings: list[str] = []
    failures: list[str] = []
    if not finite:
        failures.append("POSTERIOR_NON_FINITE")
    if not simplex:
        failures.append("PROBABILITY_SIMPLEX_INVALID")
    entropy: float | None = None
    if finite:
        entropy = float(np.mean(-np.sum(probs * np.log(np.maximum(probs, 1e-15)), axis=-1)))
        max_entropy = float(np.log(probs.shape[-1]))
        if entropy < 0.02 * max_entropy:
            warnings.append("LOW_POSTERIOR_ENTROPY")
    unique = len(set(point_predictions or [])) if point_predictions else None
    if unique == 1 and point_predictions and len(point_predictions) > 1:
        warnings.append("PREDICTION_COLLAPSE_CANDIDATE")
    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    return DiagnosticReport(
        status=status,
        backend=backend,
        inference_profile_id=inference_profile_id,
        posterior_finite=finite,
        probability_simplex_valid=simplex,
        warnings=warnings,
        failure_codes=failures,
        effective_sample_size=None,
        prediction_entropy=entropy,
        unique_point_predictions=unique,
    )
