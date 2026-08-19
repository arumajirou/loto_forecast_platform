"""Fold-level and prediction-order evidence for TAJ-21 full OOF runs."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from loto.evaluation import unified_campaign as unified
from loto.evaluation.seed_summary import SeedMetricValue, summarize_seed_metric


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value}")
    return parsed.astimezone(UTC)


def prediction_before_actual_source_contract() -> dict[str, Any]:
    """Fail closed unless the live seed evaluator seals before reading actuals."""

    source = inspect.getsource(unified._evaluate_seed)
    tree = ast.parse(source)
    lock_lines: list[int] = []
    actual_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "_write_prediction_lock":
                lock_lines.append(node.lineno)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "actual" for target in targets):
                actual_lines.append(node.lineno)
    if len(lock_lines) != 1 or len(actual_lines) != 1:
        raise AssertionError("unexpected _evaluate_seed lock/actual source contract")
    if lock_lines[0] >= actual_lines[0]:
        raise AssertionError("target actual assignment is not after prediction lock")
    return {
        "function": "loto.evaluation.unified_campaign._evaluate_seed",
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "prediction_lock_relative_line": lock_lines[0],
        "target_actual_relative_line": actual_lines[0],
        "prediction_lock_before_target_actual": True,
    }


def _position_seed_summary(
    seed_results: list[dict[str, Any]],
    expected_seeds: tuple[int, ...],
) -> dict[str, Any]:
    if not seed_results:
        return {}
    positions = tuple(seed_results[0]["metrics"]["position_hit_at_1_by_position"].keys())
    output: dict[str, Any] = {}
    for position in positions:
        values = [
            SeedMetricValue(
                seed=int(item["seed"]),
                value=float(item["metrics"]["position_hit_at_1_by_position"][position]),
            )
            for item in seed_results
        ]
        output[position] = summarize_seed_metric(
            "position_hit_at_1", values, expected_seeds=expected_seeds
        ).to_dict()
    return output


def _augment_seed(
    prepared: unified.PreparedGame,
    seed_result: dict[str, Any],
    *,
    tau: int,
    source_contract: dict[str, Any],
) -> None:
    lock_info = seed_result["prediction_lock"]
    lock_path = Path(str(lock_info["path"])).resolve()
    if not lock_path.is_file():
        raise FileNotFoundError(f"prediction lock missing: {lock_path}")
    if _sha256(lock_path) != str(lock_info["sha256"]):
        raise ValueError(f"prediction lock digest mismatch: {lock_path}")
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock_payload.get("actuals_known") is not False:
        raise ValueError(f"prediction lock exposes actuals: {lock_path}")
    records = list(lock_payload.get("predictions", []))
    if not records:
        raise ValueError(f"prediction lock has no predictions: {lock_path}")

    sealed_at = _utc(str(lock_payload["sealed_at_utc"]))
    actual_read_started = datetime.now(UTC)
    if actual_read_started <= sealed_at:
        raise AssertionError("verification actual read did not occur after prediction seal")

    by_fold: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_fold.setdefault(str(record["fold_id"]), []).append(record)

    fold_metrics: list[dict[str, Any]] = []
    for fold in prepared.folds:
        fold_id = str(fold.fold_id)
        fold_records = by_fold.get(fold_id, [])
        if not fold_records:
            raise ValueError(f"prediction evidence missing fold {fold.fold_id}")
        actual = np.asarray(
            [
                prepared.development.iloc[int(record["draw_index"])][
                    prepared.geometry.column_names()
                ].to_numpy(dtype=float)
                for record in fold_records
            ]
        )
        predicted = np.asarray([record["prediction"] for record in fold_records], dtype=float)
        fold_metrics.append(
            {
                "fold_id": fold_id,
                "draws": len(fold_records),
                "metrics": unified._canonical_metrics(
                    actual, predicted, prepared.geometry, tau=tau
                ),
            }
        )

    seed_result["fold_metrics"] = fold_metrics
    seed_result["actual_read_evidence"] = {
        "prediction_sealed_at_utc": sealed_at.isoformat(),
        "verification_actual_read_started_at_utc": actual_read_started.isoformat(),
        "verification_actual_read_completed_at_utc": datetime.now(UTC).isoformat(),
        "verification_actual_read_after_prediction_seal": True,
        "scoring_source_contract": source_contract,
    }


def augment_fold_and_seed_evidence(
    frames: dict[str, Any],
    config: unified.UnifiedCampaignConfig,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Augment successful rows without changing model predictions or aggregate metrics."""

    source_contract = prediction_before_actual_source_contract()
    prepared = {game: unified._prepare_game(game, frames[game], config) for game in config.games}
    for row in summary["results"]:
        if row["status"] != "SUCCEEDED":
            continue
        row["seed_summary"]["position_hit_at_1_by_position"] = _position_seed_summary(
            row["seed_results"], config.seeds
        )
        expected_positions = prepared[row["game"]].geometry.positions
        if len(row["seed_summary"]["position_hit_at_1_by_position"]) != expected_positions:
            raise AssertionError("per-position all-seed summary is incomplete")
        for seed_result in row["seed_results"]:
            _augment_seed(
                prepared[row["game"]],
                seed_result,
                tau=config.tau,
                source_contract=source_contract,
            )
            if len(seed_result["fold_metrics"]) != config.folds:
                raise AssertionError("fold-level metric inventory is incomplete")
    summary["prediction_before_actual_source_contract"] = source_contract
    return summary
