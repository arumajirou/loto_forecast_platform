from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


class VerificationError(RuntimeError):
    """Raised when durable sktime evidence fails closed verification."""


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or value in {"", "."}:
        raise VerificationError(f"unsafe artifact path: {value!r}")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise VerificationError(f"artifact escapes root: {value!r}") from exc
    return resolved


def verify_sha256sums(directory: Path, *, recursive: bool = False) -> list[dict[str, Any]]:
    """Verify a portable SHA256SUMS file and reject missing or extra files."""

    sums_path = directory / "SHA256SUMS"
    if not sums_path.is_file():
        raise VerificationError(f"missing SHA256SUMS: {sums_path}")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(
        sums_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        parts = raw_line.split("  ", maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise VerificationError(f"invalid SHA256SUMS line {line_number}: {raw_line!r}")
        expected, relative_name = parts
        if relative_name in seen:
            raise VerificationError(f"duplicate SHA256SUMS path: {relative_name}")
        seen.add(relative_name)
        artifact = _safe_relative_path(directory, relative_name)
        if not artifact.is_file():
            raise VerificationError(f"hashed artifact is missing: {relative_name}")
        actual = _sha256(artifact)
        if actual != expected:
            raise VerificationError(
                f"SHA-256 mismatch for {relative_name}: expected {expected}, got {actual}"
            )
        records.append(
            {
                "path": relative_name,
                "size_bytes": artifact.stat().st_size,
                "sha256": actual,
            }
        )

    pattern = "**/*" if recursive else "*"
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.glob(pattern)
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != actual_files:
        missing = sorted(actual_files - seen)
        stale = sorted(seen - actual_files)
        raise VerificationError(
            f"SHA256SUMS coverage mismatch: unhashed={missing}, stale={stale}"
        )
    if not records:
        raise VerificationError(f"SHA256SUMS contains no records: {sums_path}")
    return records


def verify_manifest(directory: Path) -> dict[str, Any]:
    """Verify the provider manifest against current file sizes and hashes."""

    manifest = _load_json(directory / "ARTIFACT_MANIFEST.json")
    if not isinstance(manifest, dict) or manifest.get("status") != "PASS":
        raise VerificationError("provider manifest status is not PASS")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise VerificationError("provider manifest files must be a non-empty list")

    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise VerificationError("provider manifest contains a non-object record")
        relative_name = str(record.get("path", ""))
        if relative_name in seen:
            raise VerificationError(f"duplicate manifest path: {relative_name}")
        seen.add(relative_name)
        artifact = _safe_relative_path(directory, relative_name)
        if not artifact.is_file():
            raise VerificationError(f"manifest artifact is missing: {relative_name}")
        if int(record.get("size_bytes", -1)) != artifact.stat().st_size:
            raise VerificationError(f"manifest size mismatch: {relative_name}")
        if str(record.get("sha256", "")) != _sha256(artifact):
            raise VerificationError(f"manifest SHA-256 mismatch: {relative_name}")

    expected = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise VerificationError(
            f"manifest coverage mismatch: expected={sorted(expected)}, got={sorted(seen)}"
        )
    return manifest


def _require_pass_response(directory: Path, operation: str) -> dict[str, Any]:
    response = _load_json(directory / "response.json")
    if not isinstance(response, dict):
        raise VerificationError("response.json must contain an object")
    if response.get("status") != "PASS":
        raise VerificationError(f"{operation} response status is not PASS")
    if response.get("operation") != operation:
        raise VerificationError(
            f"response operation mismatch: expected {operation}, got {response.get('operation')}"
        )
    expected_version = response.get("expected_sktime_version")
    actual_version = response.get("actual_sktime_version")
    if expected_version != "1.0.1" or actual_version != expected_version:
        raise VerificationError(
            f"sktime version evidence mismatch: expected={expected_version}, actual={actual_version}"
        )
    return response


def verify_inventory_bundle(directory: Path) -> dict[str, Any]:
    """Verify the dynamic forecaster inventory bundle."""

    response = _require_pass_response(directory, "inventory")
    rows = _load_json(directory / "FORECASTER_INVENTORY.json")
    summary = _load_json(directory / "INVENTORY_SUMMARY.json")
    if not isinstance(rows, list) or not rows:
        raise VerificationError("forecaster inventory must be a non-empty list")
    if not isinstance(summary, dict):
        raise VerificationError("inventory summary must contain an object")

    names = [str(row.get("name", "")) for row in rows if isinstance(row, dict)]
    if len(names) != len(rows) or any(not name for name in names):
        raise VerificationError("inventory contains an invalid row or empty name")
    if len(set(names)) != len(names):
        raise VerificationError("inventory contains duplicate estimator names")
    if names != sorted(names):
        raise VerificationError("inventory order is not deterministic")

    discovered = len(rows)
    importable = sum(row.get("import_status") == "IMPORTABLE" for row in rows)
    core = sum(row.get("dependency_state") == "CORE_COMPATIBLE" for row in rows)
    optional = sum(
        row.get("dependency_state") == "OPTIONAL_DEPENDENCY_DECLARED" for row in rows
    )
    expected_counts = {
        "discovered": discovered,
        "importable": importable,
        "core_compatible": core,
        "optional_dependency_declared": optional,
    }
    for key, expected in expected_counts.items():
        if int(summary.get(key, -1)) != expected:
            raise VerificationError(
                f"inventory summary mismatch for {key}: expected {expected}, "
                f"got {summary.get(key)}"
            )
    if summary.get("count_source") != "sktime.registry.all_estimators('forecaster')":
        raise VerificationError("inventory count source is not the sktime registry")
    if response.get("inventory") != summary:
        raise VerificationError("response inventory summary differs from persisted summary")

    verify_manifest(directory)
    sha_records = verify_sha256sums(directory)
    return {
        "status": "PASS",
        "operation": "inventory",
        "discovered": discovered,
        "importable": importable,
        "core_compatible": core,
        "optional_dependency_declared": optional,
        "sha256_records": len(sha_records),
    }


def verify_naive_bundle(directory: Path) -> dict[str, Any]:
    """Verify fit/predict/save/load/re-predict evidence for NaiveForecaster."""

    response = _require_pass_response(directory, "naive_smoke")
    smoke = _load_json(directory / "NAIVE_SMOKE.json")
    if not isinstance(smoke, dict):
        raise VerificationError("NAIVE_SMOKE.json must contain an object")
    if smoke.get("model_name") != "NaiveForecaster":
        raise VerificationError("unexpected smoke model")
    if smoke.get("device") != "cpu" or smoke.get("cpu_fallback") is not False:
        raise VerificationError("Naive smoke CPU boundary is invalid")
    if smoke.get("fit_status") != "PASS" or smoke.get("predict_status") != "PASS":
        raise VerificationError("Naive fit or predict status is not PASS")
    if smoke.get("prediction_finite") is not True:
        raise VerificationError("Naive predictions are not certified finite")

    before = smoke.get("prediction_before_save")
    after = smoke.get("prediction_after_load")
    if not isinstance(before, list) or not before:
        raise VerificationError("pre-save predictions are missing")
    if before != after:
        raise VerificationError("pre-save and post-load predictions differ")
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in before):
        raise VerificationError("Naive predictions contain non-finite values")
    if smoke.get("prediction_shape") != [len(before)]:
        raise VerificationError("Naive prediction shape does not match values")

    save_load = smoke.get("save_load")
    if not isinstance(save_load, dict) or save_load.get("status") != "PASS":
        raise VerificationError("save/load status is not PASS")
    if save_load.get("exact_prediction_match") is not True:
        raise VerificationError("save/load exact prediction match is not true")
    archive_name = str(save_load.get("artifact", ""))
    archive = _safe_relative_path(directory, archive_name)
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise VerificationError("saved NaiveForecaster archive is missing or empty")
    if save_load.get("artifact_sha256") != _sha256(archive):
        raise VerificationError("saved model archive SHA-256 mismatch")
    if response.get("smoke") != smoke:
        raise VerificationError("response smoke evidence differs from persisted smoke")

    verify_manifest(directory)
    sha_records = verify_sha256sums(directory)
    return {
        "status": "PASS",
        "operation": "naive_smoke",
        "model_name": "NaiveForecaster",
        "forecast_horizon": smoke.get("forecast_horizon"),
        "prediction_shape": smoke.get("prediction_shape"),
        "save_load": "PASS",
        "sha256_records": len(sha_records),
    }


def _write_recursive_sha256sums(run_dir: Path) -> None:
    files = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.relative_to(run_dir).as_posix() != "SHA256SUMS"
    )
    lines = [
        f"{_sha256(path)}  {path.relative_to(run_dir).as_posix()}"
        for path in files
    ]
    _atomic_write_text(run_dir / "SHA256SUMS", "\n".join(lines) + "\n")


def finalize_p0_run(run_dir: Path) -> dict[str, Any]:
    """Verify both provider bundles and finalize top-level P0 evidence."""

    run_dir = run_dir.resolve()
    inventory = verify_inventory_bundle(run_dir / "inventory")
    naive = verify_naive_bundle(run_dir / "naive-smoke")
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-core-py313-p0",
        "sktime_version": "1.0.1",
        "inventory": inventory,
        "naive_smoke": naive,
        "certification_boundaries": {
            "dynamic_inventory": "VERIFIED",
            "naive_fit_predict_save_load": "VERIFIED",
            "all_forecaster_runtime": "EXECUTION_PENDING",
            "optional_dependency_lanes": "EXECUTION_PENDING",
            "shared_worker_integration": "NOT_APPLICABLE",
            "gpu_runtime": "NOT_APPLICABLE",
            "accuracy_improvement": "NOT_CLAIMED",
        },
    }
    _write_json(run_dir / "VERIFICATION_REPORT.json", report)

    manifest_files = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file()
        and path.relative_to(run_dir).as_posix()
        not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-core-py313-p0",
        "files": [
            {
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in manifest_files
        ],
    }
    _write_json(run_dir / "ARTIFACT_MANIFEST.json", manifest)
    _write_recursive_sha256sums(run_dir)
    top_level_records = verify_sha256sums(run_dir, recursive=True)
    report["top_level_sha256_records"] = len(top_level_records)
    return report
