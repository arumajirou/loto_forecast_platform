"""Immutable campaign-level lock for prospective predictions.

The lock is written immediately after a successful prospective run receives its
promotion and lineage evidence. It binds every task prediction to the run's
configuration, data contract, promotion gate, lineage, code hash, and data hash.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .persistence import sha256_file, verify_sha256s, write_json, write_sha256s

PREDICTION_LOCK_SCHEMA_VERSION = "all-auto-prediction-lock-v1"
PREDICTION_LOCK_PATH = "PREDICTION_LOCK.json"
_PROSPECTIVE_STAGE = "prospective"
_ACTUAL_NAME_TOKENS = ("actual", "observed", "realized", "outcome")


def _read_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict) or not payload:
        failures.append(f"{label} must be a non-empty JSON object: {path}")
        return {}
    return payload


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: Any, failures: list[str], label: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        failures.append(f"{label} missing")
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{label} is not ISO-8601: {text}")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{label} must include a timezone")
        return None
    return parsed.astimezone(UTC)


def _safe_relative(value: str, failures: list[str], label: str) -> Path | None:
    if "\\" in value:
        failures.append(f"{label} contains a backslash: {value}")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts:
        failures.append(f"{label} is unsafe: {value}")
        return None
    return Path(*pure.parts)


def _reject_symlinks(root: Path) -> list[str]:
    failures: list[str] = []
    if root.is_symlink():
        return [f"prospective run root must not be a symlink: {root}"]
    if not root.is_dir():
        return [f"prospective run root is not a directory: {root}"]
    try:
        paths = list(root.rglob("*"))
    except OSError as exc:
        return [f"prospective run traversal failed: {type(exc).__name__}: {exc}"]
    for path in paths:
        if path.is_symlink():
            failures.append(
                "prospective prediction lock does not allow symlinks: "
                f"{path.relative_to(root).as_posix()}"
            )
    return failures


def _actual_artifact_failures(root: Path) -> list[str]:
    failures: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == PREDICTION_LOCK_PATH:
            continue
        folded = path.name.casefold()
        if any(token in folded for token in _ACTUAL_NAME_TOKENS):
            failures.append(f"actual-bearing artifact present before lock: {relative}")
    return failures


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"prediction lock does not allow symlinks: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    relative = path.relative_to(root).as_posix()
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _task_records(run_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    freezes = sorted(
        run_root.glob("tasks/**/prediction_freeze.json"),
        key=lambda item: item.relative_to(run_root).as_posix(),
    )
    if not freezes:
        return [], ["no task prediction_freeze.json files found"]

    records: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    for freeze_path in freezes:
        task_root = freeze_path.parent
        task_relative = task_root.relative_to(run_root).as_posix()
        if task_relative in seen_tasks:
            failures.append(f"duplicate task directory: {task_relative}")
            continue
        seen_tasks.add(task_relative)

        task_failures: list[str] = []
        task_manifest = _read_json(
            task_root / "manifest.json",
            task_failures,
            f"{task_relative} manifest",
        )
        freeze = _read_json(
            freeze_path,
            task_failures,
            f"{task_relative} prediction freeze",
        )
        load_verify = _read_json(
            task_root / "best_model/load_predict_verification.json",
            task_failures,
            f"{task_relative} load/predict verification",
        )

        if task_manifest.get("status") != "PASS":
            task_failures.append(
                f"{task_relative} manifest status is not PASS: {task_manifest.get('status')}"
            )
        task_payload = task_manifest.get("task")
        if not isinstance(task_payload, Mapping):
            task_failures.append(f"{task_relative} task manifest payload missing")
        elif task_payload.get("stage") != _PROSPECTIVE_STAGE:
            task_failures.append(
                f"{task_relative} task stage is not prospective: {task_payload.get('stage')}"
            )

        if freeze.get("actual_known") is not False:
            task_failures.append(f"{task_relative} actual_known must be false")
        task_frozen_at = _parse_utc(
            freeze.get("frozen_at"),
            task_failures,
            f"{task_relative} frozen_at",
        )

        required_flags = {
            "status": "PASS",
            "loaded": True,
            "predicted": True,
            "shape_match": True,
            "finite": True,
            "prediction_match": True,
            "cpu_fallback": False,
        }
        for key, expected in required_flags.items():
            if load_verify.get(key) != expected:
                task_failures.append(
                    f"{task_relative} load verification {key} mismatch: "
                    f"expected={expected}, actual={load_verify.get(key)}"
                )

        files: dict[str, dict[str, Any]] = {}
        for name, relative in (
            ("task_manifest", "manifest.json"),
            ("task_sha256s", "SHA256SUMS"),
            ("task_freeze", "prediction_freeze.json"),
            ("prediction_before", "best_model/prediction_before_save.parquet"),
            ("prediction_after", "best_model/prediction_after_load.parquet"),
            ("load_verification", "best_model/load_predict_verification.json"),
            ("bundle_manifest", "best_model/manifest.json"),
            ("bundle_sha256s", "best_model/SHA256SUMS"),
        ):
            try:
                files[name] = _file_record(run_root, task_root / relative)
            except (OSError, ValueError) as exc:
                task_failures.append(
                    f"{task_relative} {name} unavailable: {type(exc).__name__}: {exc}"
                )

        before = files.get("prediction_before")
        if before is not None and freeze.get("prediction_sha256") != before["sha256"]:
            task_failures.append(
                f"{task_relative} prediction_freeze SHA differs from prediction_before"
            )
        for item in verify_sha256s(task_root):
            task_failures.append(f"{task_relative} SHA256: {item}")
        for item in verify_sha256s(task_root / "best_model"):
            task_failures.append(f"{task_relative} best_model SHA256: {item}")

        if task_failures:
            failures.extend(task_failures)
            continue
        records.append(
            {
                "task_path": task_relative,
                "task": dict(task_payload),
                "task_frozen_at": task_frozen_at.isoformat(),
                "actual_known": False,
                "files": files,
            }
        )
    return records, failures


def _run_file_records(run_root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _file_record(run_root, run_root / relative)
        for name, relative in (
            ("campaign_config", "campaign_config.json"),
            ("data_contract", "data_contract.json"),
            ("promotion_gate", "PROMOTION_GATE.json"),
            ("lineage", "LINEAGE.json"),
        )
    }


def _base_lock_payload(
    run_root: Path,
    manifest: Mapping[str, Any],
    tasks: list[dict[str, Any]],
    locked_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": PREDICTION_LOCK_SCHEMA_VERSION,
        "status": "LOCKED",
        "locked_at": locked_at,
        "timestamp_authority": "LOCAL_SYSTEM_UTC",
        "actual_known": False,
        "actual_artifacts_present": False,
        "run": {
            "run_id": manifest.get("run_id"),
            "stage": manifest.get("stage"),
            "code_sha256": manifest.get("code_sha256"),
            "data_sha256": manifest.get("data_sha256"),
            "lineage_chain_sha256": manifest.get("lineage_chain_sha256"),
            "planned_tasks": manifest.get("planned_tasks"),
            "completed_tasks": manifest.get("completed_tasks"),
            "files": _run_file_records(run_root),
        },
        "task_count": len(tasks),
        "tasks": tasks,
    }


def _manifest_precondition_failures(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> list[str]:
    failures = _reject_symlinks(run_root)
    if manifest.get("status") != "PASS":
        failures.append(f"run manifest status is not PASS: {manifest.get('status')}")
    if manifest.get("stage") != _PROSPECTIVE_STAGE:
        failures.append(f"run stage is not prospective: {manifest.get('stage')}")
    if manifest.get("lineage_status") != "PASS":
        failures.append("run lineage_status must be PASS")
    if manifest.get("lineage_path") != "LINEAGE.json":
        failures.append("run lineage_path must be LINEAGE.json")
    if manifest.get("promotion_gate_status") != "PASS":
        failures.append("run promotion_gate_status must be PASS")
    for key in ("code_sha256", "data_sha256", "lineage_chain_sha256"):
        if not str(manifest.get(key) or "").strip():
            failures.append(f"run manifest {key} missing")
    failures.extend(_actual_artifact_failures(run_root))
    return failures


def _read_manifest(run_root: Path, failures: list[str]) -> dict[str, Any]:
    return _read_json(run_root / "manifest.json", failures, "run manifest")


def freeze_prospective_predictions(run_root: Path) -> dict[str, Any]:
    """Create one immutable lock for all prospective task predictions."""

    run_root = run_root.resolve()
    lock_path = run_root / PREDICTION_LOCK_PATH
    manifest_failures: list[str] = []
    manifest = _read_manifest(run_root, manifest_failures)
    if lock_path.is_file():
        result = verify_prediction_lock(run_root, manifest)
        if result.get("status") != "PASS":
            raise ValueError(
                "existing prediction lock is invalid: " + "; ".join(result.get("failures", []))
            )
        return {
            "status": "PASS",
            "prediction_lock_status": "LOCKED",
            "prediction_lock_path": PREDICTION_LOCK_PATH,
            "prediction_lock_sha256": sha256_file(lock_path),
            "prediction_task_count": result.get("task_count"),
            "prediction_locked_at": result.get("locked_at"),
            "idempotent": True,
        }
    if (run_root / "VERIFICATION_SEAL.json").exists():
        raise ValueError("sealed prospective run cannot receive a new prediction lock")

    failures = [
        *manifest_failures,
        *_manifest_precondition_failures(run_root, manifest),
    ]
    tasks, task_failures = _task_records(run_root)
    failures.extend(task_failures)
    expected_planned = manifest.get("planned_tasks")
    expected_completed = manifest.get("completed_tasks")
    if not isinstance(expected_planned, int) or expected_planned <= 0:
        failures.append("run planned_tasks must be a positive integer")
    if expected_completed != expected_planned:
        failures.append(
            "prospective run must complete all tasks before locking: "
            f"planned={expected_planned}, completed={expected_completed}"
        )
    if isinstance(expected_completed, int) and len(tasks) != expected_completed:
        failures.append(
            "prediction task count differs from completed_tasks: "
            f"locked={len(tasks)}, completed={expected_completed}"
        )
    if failures:
        raise ValueError("; ".join(failures))

    locked_at_dt = datetime.now(UTC)
    for task in tasks:
        frozen_at = _parse_utc(task.get("task_frozen_at"), failures, "task_frozen_at")
        if frozen_at is not None and frozen_at > locked_at_dt:
            failures.append(f"task freeze is later than campaign lock: {task['task_path']}")
    if failures:
        raise ValueError("; ".join(failures))

    payload = _base_lock_payload(
        run_root,
        manifest,
        tasks,
        locked_at_dt.isoformat(),
    )
    payload["lock_sha256"] = _canonical_sha256(payload)

    manifest_before = (run_root / "manifest.json").read_bytes()
    sums_path = run_root / "SHA256SUMS"
    sums_before = sums_path.read_bytes() if sums_path.is_file() else None
    temporary = lock_path.with_name(lock_path.name + ".partial")
    try:
        write_json(temporary, payload)
        os.replace(temporary, lock_path)
        updated_manifest = dict(manifest)
        updated_manifest.update(
            {
                "prediction_lock_schema_version": PREDICTION_LOCK_SCHEMA_VERSION,
                "prediction_lock_status": "LOCKED",
                "prediction_lock_path": PREDICTION_LOCK_PATH,
                "prediction_lock_sha256": sha256_file(lock_path),
                "prediction_task_count": len(tasks),
                "prediction_locked_at": payload["locked_at"],
                "actual_known_at_lock": False,
            }
        )
        write_json(run_root / "manifest.json", updated_manifest)
        write_sha256s(run_root)
        verification = verify_prediction_lock(run_root, updated_manifest)
        if verification.get("status") != "PASS":
            raise ValueError(
                "new prediction lock failed verification: "
                + "; ".join(verification.get("failures", []))
            )
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if lock_path.exists():
            lock_path.unlink()
        (run_root / "manifest.json").write_bytes(manifest_before)
        if sums_before is None:
            if sums_path.exists():
                sums_path.unlink()
        else:
            sums_path.write_bytes(sums_before)
        raise

    return {
        "status": "PASS",
        "prediction_lock_status": "LOCKED",
        "prediction_lock_path": PREDICTION_LOCK_PATH,
        "prediction_lock_sha256": sha256_file(lock_path),
        "prediction_task_count": len(tasks),
        "prediction_locked_at": payload["locked_at"],
        "lock_sha256": payload["lock_sha256"],
        "idempotent": False,
    }


def _verify_file_record(
    run_root: Path,
    record: Any,
    failures: list[str],
    label: str,
) -> None:
    if not isinstance(record, Mapping):
        failures.append(f"{label} record must be an object")
        return
    relative_text = str(record.get("path") or "")
    safe = _safe_relative(relative_text, failures, f"{label} path")
    if safe is None:
        return
    path = run_root / safe
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(run_root.resolve())
    except (OSError, ValueError):
        failures.append(f"{label} path escapes or is missing: {relative_text}")
        return
    if path.is_symlink() or not path.is_file():
        failures.append(f"{label} must be a regular file: {relative_text}")
        return
    actual_sha = sha256_file(path)
    if record.get("sha256") != actual_sha:
        failures.append(
            f"{label} SHA256 mismatch: recorded={record.get('sha256')}, actual={actual_sha}"
        )
    if record.get("size_bytes") != path.stat().st_size:
        failures.append(f"{label} size mismatch: {relative_text}")


def verify_prediction_lock(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a campaign prediction lock and every bound prediction artifact."""

    run_root = run_root.resolve()
    lock_path = run_root / PREDICTION_LOCK_PATH
    applicable = bool(
        manifest.get("stage") == _PROSPECTIVE_STAGE
        or lock_path.exists()
        or manifest.get("prediction_lock_status") is not None
    )
    if not applicable:
        return {
            "applicable": False,
            "status": "NOT_APPLICABLE",
            "task_count": 0,
            "locked_at": None,
            "failures": [],
        }

    failures = _reject_symlinks(run_root)
    lock = _read_json(lock_path, failures, "prediction lock")
    if manifest.get("stage") != _PROSPECTIVE_STAGE:
        failures.append("prediction lock is attached to a non-prospective run")
    if lock.get("schema_version") != PREDICTION_LOCK_SCHEMA_VERSION:
        failures.append("prediction lock schema_version mismatch")
    if lock.get("status") != "LOCKED":
        failures.append(f"prediction lock status is not LOCKED: {lock.get('status')}")
    if lock.get("actual_known") is not False:
        failures.append("prediction lock actual_known must be false")
    if lock.get("actual_artifacts_present") is not False:
        failures.append("prediction lock actual_artifacts_present must be false")
    locked_at = _parse_utc(lock.get("locked_at"), failures, "prediction locked_at")
    if lock.get("timestamp_authority") != "LOCAL_SYSTEM_UTC":
        failures.append("prediction lock timestamp_authority mismatch")

    if lock:
        core = {key: value for key, value in lock.items() if key != "lock_sha256"}
        expected_lock_sha = _canonical_sha256(core)
        if lock.get("lock_sha256") != expected_lock_sha:
            failures.append("prediction lock canonical lock_sha256 mismatch")

    manifest_expectations = {
        "prediction_lock_schema_version": PREDICTION_LOCK_SCHEMA_VERSION,
        "prediction_lock_status": "LOCKED",
        "prediction_lock_path": PREDICTION_LOCK_PATH,
        "prediction_lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        "prediction_task_count": lock.get("task_count"),
        "prediction_locked_at": lock.get("locked_at"),
        "actual_known_at_lock": False,
    }
    for key, expected in manifest_expectations.items():
        if manifest.get(key) != expected:
            failures.append(
                f"run manifest {key} mismatch: expected={expected}, actual={manifest.get(key)}"
            )

    run_record = lock.get("run")
    if not isinstance(run_record, Mapping):
        failures.append("prediction lock run record must be an object")
        run_record = {}
    for key in (
        "run_id",
        "stage",
        "code_sha256",
        "data_sha256",
        "lineage_chain_sha256",
        "planned_tasks",
        "completed_tasks",
    ):
        if run_record.get(key) != manifest.get(key):
            failures.append(f"prediction lock run {key} differs from manifest")
    run_files = run_record.get("files")
    if not isinstance(run_files, Mapping):
        failures.append("prediction lock run files must be an object")
    else:
        for name in ("campaign_config", "data_contract", "promotion_gate", "lineage"):
            _verify_file_record(
                run_root,
                run_files.get(name),
                failures,
                f"run {name}",
            )

    tasks = lock.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        failures.append("prediction lock tasks must be a non-empty list")
        tasks = []
    if lock.get("task_count") != len(tasks):
        failures.append("prediction lock task_count differs from tasks length")
    seen_paths: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            failures.append(f"prediction lock task {index} must be an object")
            continue
        task_path = str(task.get("task_path") or "")
        if task_path in seen_paths:
            failures.append(f"duplicate prediction lock task path: {task_path}")
        seen_paths.add(task_path)
        if task.get("actual_known") is not False:
            failures.append(f"prediction lock task actual_known is not false: {task_path}")
        frozen_at = _parse_utc(
            task.get("task_frozen_at"),
            failures,
            f"prediction lock task frozen_at {task_path}",
        )
        if locked_at is not None and frozen_at is not None and frozen_at > locked_at:
            failures.append(f"task freeze is later than campaign lock: {task_path}")
        task_payload = task.get("task")
        if not isinstance(task_payload, Mapping):
            failures.append(f"prediction lock task payload missing: {task_path}")
        elif task_payload.get("stage") != _PROSPECTIVE_STAGE:
            failures.append(f"prediction lock task stage is not prospective: {task_path}")
        files = task.get("files")
        if not isinstance(files, Mapping):
            failures.append(f"prediction lock task files missing: {task_path}")
            continue
        for name in (
            "task_manifest",
            "task_sha256s",
            "task_freeze",
            "prediction_before",
            "prediction_after",
            "load_verification",
            "bundle_manifest",
            "bundle_sha256s",
        ):
            _verify_file_record(
                run_root,
                files.get(name),
                failures,
                f"task {task_path} {name}",
            )

        freeze_record = files.get("task_freeze")
        before_record = files.get("prediction_before")
        if isinstance(freeze_record, Mapping):
            safe = _safe_relative(
                str(freeze_record.get("path") or ""),
                failures,
                f"task {task_path} freeze path",
            )
            if safe is not None and (run_root / safe).is_file():
                freeze = _read_json(
                    run_root / safe,
                    failures,
                    f"task {task_path} freeze",
                )
                if freeze.get("actual_known") is not False:
                    failures.append(f"task {task_path} freeze actual_known must be false")
                if isinstance(before_record, Mapping):
                    if freeze.get("prediction_sha256") != before_record.get("sha256"):
                        failures.append(f"task {task_path} freeze prediction SHA mismatch")

    failures.extend(_actual_artifact_failures(run_root))
    return {
        "applicable": True,
        "status": "PASS" if not failures else "FAIL",
        "schema_version": lock.get("schema_version"),
        "task_count": len(tasks),
        "locked_at": lock.get("locked_at"),
        "lock_sha256": lock.get("lock_sha256"),
        "timestamp_authority": lock.get("timestamp_authority"),
        "failures": failures,
    }
