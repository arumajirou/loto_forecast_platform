"""Provider-neutral save/reload and prediction replay comparison."""

from __future__ import annotations

from typing import Any

from .contracts import ReplayEvidence
from .identity import canonical_json_bytes, sha256_bytes
from .output_validation import flatten_numbers


class ReplayValidationError(RuntimeError):
    pass


def maximum_absolute_difference(first: Any, second: Any) -> float:
    first_values = flatten_numbers(first)
    second_values = flatten_numbers(second)
    if len(first_values) != len(second_values):
        return float("inf")
    if not first_values:
        return 0.0
    return max(abs(left - right) for left, right in zip(first_values, second_values, strict=True))


def compare_replay(
    first: Any,
    second: Any,
    *,
    first_process_pid: int,
    second_process_pid: int,
    tolerance: float = 0.0,
    save_succeeded: bool = True,
    reload_succeeded: bool = True,
    re_predict_succeeded: bool = True,
) -> ReplayEvidence:
    if tolerance < 0:
        raise ReplayValidationError("tolerance must be non-negative")
    if first_process_pid == second_process_pid:
        raise ReplayValidationError("replay requires distinct provider process IDs")
    first_sha256 = sha256_bytes(canonical_json_bytes(first))
    second_sha256 = sha256_bytes(canonical_json_bytes(second))
    difference = maximum_absolute_difference(first, second)
    exact = first_sha256 == second_sha256
    if not exact and difference > tolerance:
        raise ReplayValidationError(
            f"replay differs: max_abs_diff={difference}, tolerance={tolerance}"
        )
    return ReplayEvidence(
        save_succeeded=save_succeeded,
        reload_succeeded=reload_succeeded,
        re_predict_succeeded=re_predict_succeeded,
        distinct_processes=first_process_pid != second_process_pid,
        first_process_pid=first_process_pid,
        second_process_pid=second_process_pid,
        first_output_sha256=first_sha256,
        second_output_sha256=second_sha256,
        exact_match=exact,
        maximum_absolute_difference=difference,
        tolerance=tolerance,
    )
