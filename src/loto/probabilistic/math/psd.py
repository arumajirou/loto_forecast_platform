from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatMatrix = NDArray[np.float64]


@dataclass(frozen=True)
class PSDValidation:
    """Machine-readable evidence for a positive-semidefinite matrix check."""

    matrix: FloatMatrix
    is_psd: bool
    symmetrized: bool
    repaired: bool
    jitter_added: float
    min_eigenvalue_before: float
    min_eigenvalue_after: float
    tolerance: float


def validate_psd(
    matrix: ArrayLike,
    *,
    tolerance: float = 1e-10,
    repair: bool = False,
    jitter_floor: float = 1e-12,
) -> PSDValidation:
    """Validate and optionally repair a finite square PSD matrix.

    Repair is explicit and recorded. It consists only of symmetrization plus a
    diagonal jitter large enough to move the minimum eigenvalue above zero.
    """

    values = np.asarray(matrix, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("matrix must be square")
    if values.shape[0] == 0:
        raise ValueError("matrix must not be empty")
    if not np.isfinite(values).all():
        raise ValueError("matrix must contain only finite values")
    if tolerance < 0.0 or jitter_floor <= 0.0:
        raise ValueError("tolerance must be nonnegative and jitter_floor must be positive")

    symmetrized_matrix = (values + values.T) / 2.0
    symmetrized = not np.allclose(values, values.T, atol=tolerance, rtol=0.0)
    min_before = float(np.linalg.eigvalsh(symmetrized_matrix).min())
    repaired = False
    jitter = 0.0
    output = symmetrized_matrix

    if min_before < -tolerance and repair:
        jitter = -min_before + jitter_floor
        output = symmetrized_matrix + np.eye(values.shape[0], dtype=np.float64) * jitter
        repaired = True

    min_after = float(np.linalg.eigvalsh(output).min())
    return PSDValidation(
        matrix=output,
        is_psd=min_after >= -tolerance,
        symmetrized=symmetrized,
        repaired=repaired,
        jitter_added=float(jitter),
        min_eigenvalue_before=min_before,
        min_eigenvalue_after=min_after,
        tolerance=float(tolerance),
    )


def require_psd(
    matrix: ArrayLike,
    *,
    tolerance: float = 1e-10,
    repair: bool = False,
    jitter_floor: float = 1e-12,
) -> PSDValidation:
    """Return PSD evidence or raise a fail-closed ``ValueError``."""

    result = validate_psd(
        matrix,
        tolerance=tolerance,
        repair=repair,
        jitter_floor=jitter_floor,
    )
    if not result.is_psd:
        raise ValueError(
            "PSD_VIOLATION: "
            f"minimum eigenvalue {result.min_eigenvalue_after:.6e} is below "
            f"tolerance {-result.tolerance:.6e}"
        )
    return result
