"""Read-only verification for Prospective actual scoring artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .persistence import sha256_file, verify_sha256s
from .prediction_lock import PREDICTION_LOCK_PATH, verify_prediction_lock
from .prospective_scoring_support import (
    ACTUALS_LOCK,
    ACTUALS_LOCK_SCHEMA_VERSION,
    ARTIFACT_MANIFEST,
    SCORING_REPORT,
    SCORING_SCHEMA_VERSION,
    _canonical_sha256,
    _read_json,
    _reject_symlinks,
    _safe_relative,
    _verify_scoring_sha256s,
)
from .verification_seal import verify_verification_seal


def verify_prospective_scoring(root: Path) -> dict[str, Any]:
    """Verify a self-contained scoring artifact without changing it."""

    root = root.resolve()
    failures = _reject_symlinks(root, "scoring artifact")
    failures.extend(f"sha256:{item}" for item in _verify_scoring_sha256s(root))
    manifest = _read_json(root / ARTIFACT_MANIFEST, failures, "artifact manifest")
    actuals_lock = _read_json(root / ACTUALS_LOCK, failures, "actuals lock")
    report = _read_json(root / SCORING_REPORT, failures, "scoring report")
    source_lock = _read_json(
        root / "source_evidence" / PREDICTION_LOCK_PATH,
        failures,
        "copied prediction lock",
    )
    prediction_map_path = root / "SOURCE_PREDICTION_MAP.json"
    try:
        prediction_map = json.loads(prediction_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"source prediction map unreadable: {type(exc).__name__}: {exc}")
        prediction_map = []

    if manifest.get("schema_version") != SCORING_SCHEMA_VERSION:
        failures.append("artifact manifest schema_version mismatch")
    if manifest.get("status") != "PASS":
        failures.append("artifact manifest status must be PASS")
    if report.get("schema_version") != SCORING_SCHEMA_VERSION:
        failures.append("scoring report schema_version mismatch")
    if report.get("status") != "PASS":
        failures.append("scoring report status must be PASS")
    if actuals_lock.get("schema_version") != ACTUALS_LOCK_SCHEMA_VERSION:
        failures.append("actuals lock schema_version mismatch")
    if actuals_lock.get("status") != "LOCKED":
        failures.append("actuals lock status must be LOCKED")
    if actuals_lock.get("actual_known") is not True:
        failures.append("actuals lock actual_known must be true")
    if actuals_lock:
        core = {key: value for key, value in actuals_lock.items() if key != "lock_sha256"}
        if actuals_lock.get("lock_sha256") != _canonical_sha256(core):
            failures.append("actuals lock canonical hash mismatch")
    if manifest:
        core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if manifest.get("manifest_sha256") != _canonical_sha256(core):
            failures.append("artifact manifest canonical hash mismatch")
        if manifest.get("actuals_lock_sha256") != (
            sha256_file(root / ACTUALS_LOCK) if (root / ACTUALS_LOCK).is_file() else None
        ):
            failures.append("artifact manifest actuals lock hash mismatch")
        if manifest.get("scoring_report_sha256") != (
            sha256_file(root / SCORING_REPORT) if (root / SCORING_REPORT).is_file() else None
        ):
            failures.append("artifact manifest scoring report hash mismatch")

    evidence_lock = root / "source_evidence" / PREDICTION_LOCK_PATH
    evidence_seal = root / "source_evidence" / "VERIFICATION_SEAL.json"
    if evidence_lock.is_file() and actuals_lock.get("prediction_lock_sha256") != sha256_file(
        evidence_lock
    ):
        failures.append("actuals lock prediction_lock_sha256 mismatch")
    if evidence_seal.is_file() and actuals_lock.get("verification_seal_sha256") != sha256_file(
        evidence_seal
    ):
        failures.append("actuals lock verification_seal_sha256 mismatch")

    source_tasks = source_lock.get("tasks")
    source_by_path: dict[str, Mapping[str, Any]] = {}
    if isinstance(source_tasks, list):
        for item in source_tasks:
            if isinstance(item, Mapping):
                source_by_path[str(item.get("task_path") or "")] = item
    else:
        failures.append("copied prediction lock tasks missing")
    if not isinstance(prediction_map, list) or not prediction_map:
        failures.append("source prediction map must be a non-empty list")
        prediction_map = []
    if manifest.get("prediction_copy_count") != len(prediction_map):
        failures.append("artifact manifest prediction_copy_count mismatch")
    if source_by_path and len(prediction_map) != len(source_by_path):
        failures.append("prediction copy count differs from prediction lock task count")
    seen_task_paths: set[str] = set()
    seen_copy_paths: set[str] = set()
    for index, item in enumerate(prediction_map):
        if not isinstance(item, Mapping):
            failures.append(f"prediction map item {index} is not an object")
            continue
        task_path = str(item.get("task_path") or "")
        copy_text = str(item.get("copied_prediction_path") or "")
        if task_path in seen_task_paths:
            failures.append(f"duplicate prediction map task: {task_path}")
        seen_task_paths.add(task_path)
        if copy_text in seen_copy_paths:
            failures.append(f"duplicate prediction copy path: {copy_text}")
        seen_copy_paths.add(copy_text)
        source_task = source_by_path.get(task_path)
        if source_task is None:
            failures.append(f"prediction map task absent from lock: {task_path}")
            continue
        files = source_task.get("files")
        locked_record = files.get("prediction_before") if isinstance(files, Mapping) else None
        locked_sha = (
            str(locked_record.get("sha256") or "")
            if isinstance(locked_record, Mapping)
            else ""
        )
        if item.get("source_prediction_sha256") != locked_sha:
            failures.append(f"prediction map locked SHA mismatch: {task_path}")
        relative_failures: list[str] = []
        relative = _safe_relative(
            copy_text,
            relative_failures,
            f"prediction copy {task_path}",
        )
        failures.extend(relative_failures)
        if relative is None:
            continue
        copy_path = root / relative
        if not copy_path.is_file() or copy_path.is_symlink():
            failures.append(f"copied prediction missing: {task_path}")
            continue
        current_sha = sha256_file(copy_path)
        if current_sha != locked_sha or current_sha != item.get("copied_prediction_sha256"):
            failures.append(f"copied prediction SHA mismatch: {task_path}")

    required_tables = (
        "ACTUALS_NORMALIZED.parquet",
        "MODEL_PREDICTIONS.parquet",
        "BASELINE_PREDICTIONS.parquet",
        "SCORED_PREDICTIONS.parquet",
        "METRICS.parquet",
        "POSITION_METRICS.parquet",
        "SEED_SUMMARY.parquet",
        "RANKING.parquet",
        "BASELINE_COMPARISON.parquet",
    )
    for name in required_tables:
        if not (root / name).is_file():
            failures.append(f"required scoring table missing: {name}")

    source_text = str(manifest.get("source_run") or "").strip()
    original_source = Path(source_text) if source_text else None
    source_reverification = "NOT_AVAILABLE"
    if original_source is not None and original_source.is_dir():
        try:
            original_manifest = json.loads(
                (original_source / "manifest.json").read_text(encoding="utf-8")
            )
            prediction_result = verify_prediction_lock(original_source, original_manifest)
            seal_result = verify_verification_seal(original_source)
            sha_failures = verify_sha256s(original_source)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"original source re-verification failed: {type(exc).__name__}: {exc}")
            source_reverification = "FAIL"
        else:
            source_reverification = (
                "PASS"
                if prediction_result.get("status") == "PASS"
                and seal_result.get("status") == "PASS"
                and not sha_failures
                else "FAIL"
            )
            if source_reverification == "FAIL":
                failures.append("original source run no longer verifies")

    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": manifest.get("schema_version"),
        "source_run": manifest.get("source_run"),
        "source_reverification": source_reverification,
        "prediction_copy_count": len(prediction_map),
        "failures": failures,
    }
