from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from loto.adapters.timesfm25.contracts import TimesFM25Request, TimesFM25Response


@dataclass(frozen=True)
class ReloadVerification:
    status: str
    snapshot_path: str
    median_max_abs_diff: float
    mean_max_abs_diff: float
    quantile_max_abs_diff: float
    tolerance: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verify_separate_process_reload(
    execute: Callable[[TimesFM25Request], TimesFM25Response],
    request: TimesFM25Request,
    *,
    tolerance: float = 1e-5,
) -> ReloadVerification:
    first_request = request.model_copy(update={"operation": "predict", "snapshot_path": None})
    first = execute(first_request)
    second_request = request.model_copy(
        update={
            "operation": "reload_predict",
            "snapshot_path": first.artifact_reference.snapshot_path,
        }
    )
    second = execute(second_request)
    if not second.artifact_reference.snapshot_reloaded:
        raise ValueError("reload response did not certify snapshot_reloaded")
    if first.artifact_reference.revision != second.artifact_reference.revision:
        raise ValueError("checkpoint revision changed across reload")
    median_diff = _max_abs_diff(first.median_forecast, second.median_forecast)
    mean_diff = _max_abs_diff(first.mean_forecast, second.mean_forecast)
    quantile_diff = max(
        _max_abs_diff(first.quantiles[key], second.quantiles[key]) for key in first.quantiles
    )
    maximum = max(median_diff, mean_diff, quantile_diff)
    return ReloadVerification(
        status="PASS" if maximum <= tolerance else "FAILED",
        snapshot_path=first.artifact_reference.snapshot_path,
        median_max_abs_diff=median_diff,
        mean_max_abs_diff=mean_diff,
        quantile_max_abs_diff=quantile_diff,
        tolerance=tolerance,
    )


def _max_abs_diff(left: list[list[float]], right: list[list[float]]) -> float:
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    if left_array.shape != right_array.shape:
        raise ValueError(f"reload shape mismatch: {left_array.shape} != {right_array.shape}")
    return float(np.max(np.abs(left_array - right_array)))
