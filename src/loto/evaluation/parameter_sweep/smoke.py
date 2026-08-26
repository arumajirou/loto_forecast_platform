"""One-config real-execution smoke for every canonical Bingo5 identity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from loto.evaluation.resumable_campaign import (
    UnifiedCampaignResumeConfig,
    run_resumable_unified_campaign,
)
from loto.evaluation.unified_campaign import UnifiedCampaignConfig

from .artifacts import atomic_write_json
from .contracts import FailureCategory

_EXPECTED_IDENTITIES = 250
_EXPECTED_NEGATIVE_IDS = {"sf-nanmodel"}
_KNOWN_NOT_ROUTABLE_IDS = {"sf-sklearnmodel"}
_HOLDOUT_SIZE = 50


def classify_failure(row: Mapping[str, Any]) -> FailureCategory | None:
    """Normalize raw fail-visible campaign evidence without hiding the original error."""

    status = str(row.get("status", ""))
    if status == "SUCCEEDED":
        return None
    if status == "UNAVAILABLE":
        return FailureCategory.DEPENDENCY_ERROR

    texts = [str(row.get("reason", ""))]
    for item in row.get("failures", []) or []:
        if isinstance(item, Mapping):
            texts.extend([str(item.get("type", "")), str(item.get("reason", ""))])
        else:
            texts.append(str(item))
    text = " ".join(texts).lower()

    if "cuda out of memory" in text or "outofmemory" in text or " out of memory" in text:
        return FailureCategory.OOM
    if "cuda" in text:
        return FailureCategory.CUDA_ERROR
    if "nan" in text or "inf" in text or "non-finite" in text or "nonfinite" in text:
        return FailureCategory.NONFINITE_OUTPUT
    if "shape" in text:
        return FailureCategory.OUTPUT_SHAPE_INVALID
    if "timeout" in text or "timed out" in text:
        return FailureCategory.TIMEOUT
    if "modulenotfound" in text or "importerror" in text or "unavailable" in text:
        return FailureCategory.DEPENDENCY_ERROR
    if ("missing" in text and "argument" in text) or "required positional argument" in text:
        return FailureCategory.CONSTRUCTOR_ERROR
    if "constructor" in text or "__init__" in text:
        return FailureCategory.CONSTRUCTOR_ERROR
    if "parameter" in text or "unexpected keyword" in text or "invalid" in text:
        return FailureCategory.INVALID_PARAMETER
    if "not enough" in text or "season" in text or "precondition" in text:
        return FailureCategory.DATA_PRECONDITION
    if "predict" in text or "forecast" in text:
        return FailureCategory.PREDICT_FAILED
    if "fit" in text or "train" in text:
        return FailureCategory.FIT_FAILED
    return FailureCategory.UNKNOWN


def normalized_smoke_status(row: Mapping[str, Any]) -> str:
    candidate_id = str(row.get("candidate_id", ""))
    raw_status = str(row.get("status", "UNKNOWN"))
    if candidate_id in _EXPECTED_NEGATIVE_IDS:
        return "EXPECTED_NEGATIVE_CONTROL"
    if candidate_id in _KNOWN_NOT_ROUTABLE_IDS:
        return "NOT_ROUTABLE"
    return raw_status


def _failure_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in results:
        if row.get("source") == "baseline" or row.get("status") == "SUCCEEDED":
            continue
        category = classify_failure(row)
        failures.append(
            {
                "game": row.get("game"),
                "candidate_id": row.get("candidate_id"),
                "source": row.get("source"),
                "library": row.get("library"),
                "task": row.get("task"),
                "raw_status": row.get("status"),
                "normalized_status": normalized_smoke_status(row),
                "failure_category": category.value if category is not None else None,
                "reason": row.get("reason", ""),
                "failures": row.get("failures", []),
            }
        )
    return failures


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False))
            handle.write("\n")


def run_bingo5_smoke(
    frame: pd.DataFrame,
    *,
    run_root: Path,
    input_sha256: str,
    git_commit: str,
    device: str = "auto",
    precision: str = "32",
    max_steps: int = 1,
    wall_time_seconds: int = 300,
    gpu_count: int = 0,
    gpu_memory_bytes: int = 0,
) -> dict[str, Any]:
    """Execute one real chronological prediction per seed=42 identity, excluding Holdout."""

    smoke_root = run_root.resolve() / "smoke"
    output = smoke_root / "artifacts"
    checkpoint = smoke_root / "checkpoints"
    if output.exists() or checkpoint.exists():
        raise FileExistsError(
            "smoke output/checkpoint already exists; use the resumable campaign directly for resume"
        )

    development_rows = int(len(frame)) - _HOLDOUT_SIZE
    if development_rows <= 1:
        raise ValueError("Bingo5 frame is too short after sealing Holdout")
    min_train_size = max(2, min(100, development_rows - 1))
    config = UnifiedCampaignConfig(
        output_dir=output,
        git_commit=git_commit,
        games=("bingo5",),
        model_ids=None,
        seeds=(42,),
        folds=1,
        test_size=1,
        min_train_size=min_train_size,
        holdout_size=_HOLDOUT_SIZE,
        gap=0,
        device=device,
        precision=precision,
        max_trials=1,
        parallel_trials=1,
        wall_time_seconds=wall_time_seconds,
        max_steps=max_steps,
        gpu_count=gpu_count,
        gpu_memory_bytes=gpu_memory_bytes,
    )
    resume = UnifiedCampaignResumeConfig(
        checkpoint_dir=checkpoint,
        input_sha256={"bingo5": input_sha256},
    )
    summary = run_resumable_unified_campaign({"bingo5": frame}, config, resume=resume)
    candidate_results = [
        row
        for row in summary["results"]
        if row.get("source") in {"catalog", "probabilistic"}
    ]
    if len(candidate_results) != _EXPECTED_IDENTITIES:
        raise AssertionError(
            f"smoke result identity mismatch: expected={_EXPECTED_IDENTITIES} "
            f"observed={len(candidate_results)}"
        )
    if len({str(row["candidate_id"]) for row in candidate_results}) != _EXPECTED_IDENTITIES:
        raise AssertionError("smoke results contain duplicate/missing candidate identities")

    normalized_counts: dict[str, int] = {}
    for row in candidate_results:
        status = normalized_smoke_status(row)
        normalized_counts[status] = normalized_counts.get(status, 0) + 1

    failures = _failure_rows(candidate_results)
    atomic_write_json(
        run_root / "SMOKE_RESULTS.json",
        {
            "schema_version": "bingo5-all-identity-smoke-v1",
            "game": "bingo5",
            "seed": 42,
            "folds": 1,
            "test_size": 1,
            "holdout_size": _HOLDOUT_SIZE,
            "candidate_total": len(candidate_results),
            "normalized_status_counts": normalized_counts,
            "prediction_lock_required_for_success": True,
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "results": candidate_results,
        },
    )
    _write_jsonl(run_root / "FAILURES.jsonl", failures)
    return {
        "candidate_total": len(candidate_results),
        "normalized_status_counts": normalized_counts,
        "failures": failures,
        "output": str(output),
        "checkpoint": str(checkpoint),
    }
