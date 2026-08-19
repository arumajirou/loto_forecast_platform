"""Artifact and verification-report helpers for TAJ-21 formal OOF runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS
from loto.evaluation.protocol_v2 import canonical_json_bytes


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def build_verification_report(
    summary: dict[str, Any],
    comparisons: dict[str, Any],
    *,
    git_commit: str,
    folds: int,
) -> dict[str, Any]:
    results = list(summary["results"])
    candidates = [row for row in results if row["source"] in {"catalog", "probabilistic"}]
    baselines = [row for row in results if row["source"] == "baseline"]
    expected_baselines = len(REQUIRED_BASELINE_IDS) * len(summary["games"])

    fold_complete = True
    position_complete = True
    ordering_complete = True
    successful_seed_results = 0
    for row in results:
        if row["status"] != "SUCCEEDED":
            continue
        position = row.get("seed_summary", {}).get("position_hit_at_1_by_position", {})
        if not position:
            position_complete = False
        for seed_result in row.get("seed_results", []):
            successful_seed_results += 1
            if len(seed_result.get("fold_metrics", [])) != folds:
                fold_complete = False
            evidence = seed_result.get("actual_read_evidence", {})
            source = evidence.get("scoring_source_contract", {})
            if not evidence.get("verification_actual_read_after_prediction_seal"):
                ordering_complete = False
            if not source.get("prediction_lock_before_target_actual"):
                ordering_complete = False

    comparison_rows = list(comparisons["comparisons"])
    valid_comparisons = [item for item in comparison_rows if item["comparison_status"] == "VALID"]
    report = {
        "schema_version": "taj21-full-verification-report-v1",
        "status": "PASS",
        "git_commit": git_commit,
        "games": list(summary["games"]),
        "catalog_models": int(summary["catalog_models"]),
        "expected_model_game_pairs": int(summary["expected_model_game_pairs"]),
        "observed_model_game_pairs": int(summary["observed_model_game_pairs"]),
        "matrix_complete": bool(summary["matrix_complete"]),
        "candidate_rows": len(candidates),
        "candidate_succeeded": sum(row["status"] == "SUCCEEDED" for row in candidates),
        "baseline_rows": len(baselines),
        "expected_baseline_rows": expected_baselines,
        "baseline_succeeded": sum(row["status"] == "SUCCEEDED" for row in baselines),
        "successful_seed_results": successful_seed_results,
        "fold_metrics_per_seed": folds,
        "fold_evidence_complete": fold_complete,
        "all_seed_per_position_summary_complete": position_complete,
        "prediction_before_actual_source_contract": summary.get(
            "prediction_before_actual_source_contract"
        ),
        "post_seal_actual_read_evidence_complete": ordering_complete,
        "paired_comparison_rows": len(comparison_rows),
        "paired_valid_rows": len(valid_comparisons),
        "paired_reference_baseline": comparisons["reference_baseline"],
        "pairing_unit": comparisons["pairing_unit"],
        "multiplicity_correction": comparisons["multiplicity_correction"],
        "primary_metric": summary["primary_metric"],
        "synthetic": False,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
    }
    if not report["matrix_complete"]:
        raise AssertionError("formal candidate matrix is incomplete")
    if len(baselines) != expected_baselines or report["baseline_succeeded"] != expected_baselines:
        raise AssertionError("formal baseline matrix is incomplete")
    if not fold_complete:
        raise AssertionError("fold-level metric evidence is incomplete")
    if not position_complete:
        raise AssertionError("all-seed per-position summaries are incomplete")
    if not ordering_complete:
        raise AssertionError("prediction-before-actual evidence is incomplete")
    if len(comparison_rows) != len(candidates):
        raise AssertionError("paired comparison inventory is incomplete")
    return report


def write_artifact_manifest(output: Path, *, git_commit: str) -> dict[str, Any]:
    artifacts = sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "taj21-artifact-manifest-v1",
        "git_commit": git_commit,
        "entries": [
            {
                "path": path.relative_to(output).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in artifacts
        ],
        "self_excluded": True,
        "sha256sums_excluded": True,
    }
    write_json(output / "ARTIFACT_MANIFEST.json", manifest)
    return manifest


def regenerate_sha256sums(output: Path) -> str:
    artifacts = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(output).as_posix()}" for path in artifacts]
    sums = output / "SHA256SUMS"
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sha256_file(sums)
