from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def compare_native_outputs(first: Path, second: Path) -> dict[str, object]:
    first_array = np.load(first, allow_pickle=False)
    second_array = np.load(second, allow_pickle=False)
    same_shape = first_array.shape == second_array.shape
    exact_equal = bool(same_shape and np.array_equal(first_array, second_array))
    max_abs_diff = (
        float(np.max(np.abs(first_array - second_array)))
        if same_shape and first_array.size
        else None
    )
    return {
        "first_path": str(first),
        "second_path": str(second),
        "first_sha256": sha256_file(first),
        "second_sha256": sha256_file(second),
        "first_shape": list(first_array.shape),
        "second_shape": list(second_array.shape),
        "same_shape": same_shape,
        "exact_equal": exact_equal,
        "max_abs_diff": max_abs_diff,
    }
