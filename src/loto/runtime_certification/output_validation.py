"""Provider-neutral shape, finite-value, and quantile validation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .contracts import OutputContract, OutputEvidence
from .identity import canonical_json_bytes, sha256_bytes


class OutputValidationError(RuntimeError):
    pass


def infer_shape(value: Any) -> list[int]:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OutputValidationError(f"unsupported output value: {type(value).__name__}")
    length = len(value)
    if length == 0:
        return [0]
    child_shapes = [infer_shape(item) for item in value]
    if any(shape != child_shapes[0] for shape in child_shapes[1:]):
        raise OutputValidationError("output is ragged")
    return [length, *child_shapes[0]]


def flatten_numbers(value: Any) -> list[float]:
    if isinstance(value, bool):
        raise OutputValidationError("boolean output values are not numeric forecasts")
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[float] = []
        for item in value:
            result.extend(flatten_numbers(item))
        return result
    raise OutputValidationError(f"unsupported output value: {type(value).__name__}")


def _iter_quantile_vectors(value: Any, axis: int) -> list[list[float]]:
    shape = infer_shape(value)
    if axis >= len(shape):
        raise OutputValidationError("quantile axis is outside output shape")

    def collect(node: Any, depth: int) -> list[list[float]]:
        if depth == axis:
            sequence = list(node)
            tail_shape = shape[axis + 1 :]
            if not tail_shape:
                return [[float(item) for item in sequence]]
            child_vectors = [flatten_numbers(item) for item in sequence]
            width = len(child_vectors[0])
            if any(len(vector) != width for vector in child_vectors):
                raise OutputValidationError("quantile slices have inconsistent sizes")
            return [
                [child_vectors[quantile][index] for quantile in range(len(sequence))]
                for index in range(width)
            ]
        vectors: list[list[float]] = []
        for child in node:
            vectors.extend(collect(child, depth + 1))
        return vectors

    return collect(value, 0)


def validate_output(value: Any, contract: OutputContract) -> OutputEvidence:
    observed_shape = infer_shape(value)
    if observed_shape != contract.expected_shape:
        raise OutputValidationError(
            f"output shape mismatch: expected {contract.expected_shape}, got {observed_shape}"
        )
    numbers = flatten_numbers(value)
    if not numbers or not all(math.isfinite(item) for item in numbers):
        raise OutputValidationError("output contains non-finite or empty values")
    quantile_monotonic: bool | None = None
    if contract.quantile_axis is not None:
        quantile_monotonic = True
        for vector in _iter_quantile_vectors(value, contract.quantile_axis):
            if any(
                right + contract.monotonic_tolerance < left
                for left, right in zip(vector, vector[1:], strict=False)
            ):
                quantile_monotonic = False
                break
        if not quantile_monotonic:
            raise OutputValidationError("quantile outputs are not monotonic")
    return OutputEvidence(
        observed_shape=observed_shape,
        finite=True,
        quantile_monotonic=quantile_monotonic,
        output_sha256=sha256_bytes(canonical_json_bytes(value)),
    )
