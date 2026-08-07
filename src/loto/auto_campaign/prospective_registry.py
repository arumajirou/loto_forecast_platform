"""Register verified Prospective scoring artifacts in PostgreSQL and MLflow."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .persistence import sha256_file, verify_sha256s, write_json, write_sha256s
from .prospective_registry_contract import (
    BACKEND_RECEIPTS,
    REGISTRY_MANIFEST,
    REGISTRY_PAYLOAD,
    REGISTRY_REPORT,
    REGISTRY_SCHEMA_VERSION,
    RegistryBackendFunctions,
    RegistryOptions,
    _canonical_sha256,
)
from .prospective_registry_payload import (
    _build_payload,
    _copy_source_evidence,
    _read_json,
    _read_registry_tables,
    _registry_file_inventory,
    _safe_error,
)
from .prospective_scoring_verification import verify_prospective_scoring

# Re-export focused helpers used by existing tests and audit tooling.
from .prospective_registry_payload import _position_metric_frame as _position_metric_frame


def register_prospective_scoring(
    *,
    scoring_root: Path,
    output: Path,
    options: RegistryOptions,
    backends: RegistryBackendFunctions | None = None,
) -> dict[str, Any]:
    """Persist one verified scoring artifact to PostgreSQL and MLflow."""

    scoring_root = scoring_root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if output == scoring_root or scoring_root in output.parents:
        raise ValueError("registry receipt must be outside the scoring artifact")
    verification = verify_prospective_scoring(scoring_root)
    if verification.get("status") != "PASS":
        raise ValueError(
            "Prospective scoring artifact verification failed: "
            + "; ".join(verification.get("failures", []))
        )
    tables = _read_registry_tables(scoring_root)
    payload, frames = _build_payload(scoring_root, options, tables)
    backend_functions = backends or RegistryBackendFunctions()
    dsn = os.getenv(options.postgres_dsn_env, "")
    mlflow_uri = options.mlflow_uri or os.getenv(options.mlflow_uri_env, "")
    attempt_started_at = datetime.now(UTC).isoformat()
    receipts: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    registration_status = "PASS"

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="prospective-registry-",
        dir=output.parent,
    ) as temp:
        work = Path(temp) / "receipt"
        work.mkdir()
        copied = _copy_source_evidence(scoring_root, work)
        write_json(work / REGISTRY_PAYLOAD, payload)

        if not dsn:
            failures.append(
                {
                    "phase": "POSTGRES_PREPARE",
                    "error_type": "ConfigurationError",
                    "error": (
                        f"PostgreSQL DSN is missing; set "
                        f"{options.postgres_dsn_env}"
                    ),
                }
            )
            registration_status = "BLOCKED"
        else:
            try:
                receipts["postgres_prepare"] = (
                    backend_functions.prepare_postgres(
                        dsn,
                        payload,
                        frames,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    _safe_error(
                        exc,
                        secrets=(dsn, mlflow_uri),
                        phase="POSTGRES_PREPARE",
                    )
                )
                registration_status = "BLOCKED"

        if registration_status == "PASS":
            if not mlflow_uri:
                failures.append(
                    {
                        "phase": "MLFLOW_RECORD",
                        "error_type": "ConfigurationError",
                        "error": (
                            f"MLflow URI is missing; pass mlflow_uri or set "
                            f"{options.mlflow_uri_env}"
                        ),
                    }
                )
                registration_status = "BLOCKED"
            else:
                try:
                    receipts["mlflow"] = backend_functions.record_mlflow(
                        mlflow_uri,
                        options.mlflow_experiment,
                        payload,
                        frames,
                        evidence_root=work,
                        scoring_root=scoring_root,
                        artifact_mode=options.artifact_mode,
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        _safe_error(
                            exc,
                            secrets=(dsn, mlflow_uri),
                            phase="MLFLOW_RECORD",
                        )
                    )
                    registration_status = "BLOCKED"

        if registration_status == "PASS":
            try:
                receipts["postgres_finalize"] = (
                    backend_functions.finalize_postgres(
                        dsn,
                        payload,
                        receipts["mlflow"],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    _safe_error(
                        exc,
                        secrets=(dsn, mlflow_uri),
                        phase="POSTGRES_FINALIZE",
                    )
                )
                registration_status = "BLOCKED"

        if registration_status != "PASS" and dsn and "postgres_prepare" in receipts:
            try:
                receipts["postgres_blocked"] = (
                    backend_functions.mark_postgres_blocked(
                        dsn,
                        payload,
                        failures[-1],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                receipts["postgres_blocked"] = {
                    "backend": "postgres",
                    "status": "BLOCKED",
                    **_safe_error(
                        exc,
                        secrets=(dsn, mlflow_uri),
                        phase="POSTGRES_MARK_BLOCKED",
                    ),
                }

        backend_receipt_payload = {
            "attempted": sorted(receipts),
            "receipts": receipts,
        }
        write_json(work / BACKEND_RECEIPTS, backend_receipt_payload)
        report = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "status": registration_status,
            "registry_id": payload["registry_id"],
            "registry_namespace": payload["registry_namespace"],
            "scoring_id": payload["scoring_id"],
            "payload_sha256": payload["payload_sha256"],
            "attempt_started_at": attempt_started_at,
            "attempt_finished_at": datetime.now(UTC).isoformat(),
            "source_scoring_status": verification.get("status"),
            "source_reverification": "PASS",
            "required_backends": ["postgres", "mlflow"],
            "receipts": receipts,
            "failures": failures,
            "source_evidence": copied,
            "counts": payload["counts"],
            "safety": {
                "source_scoring_mutated": False,
                "automatic_promotion": False,
                "automatic_retraining": False,
                "best_seed_only_selection": False,
                "secrets_persisted": False,
            },
        }
        write_json(work / REGISTRY_REPORT, report)
        manifest: dict[str, Any] = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "status": registration_status,
            "registry_id": payload["registry_id"],
            "scoring_id": payload["scoring_id"],
            "payload_sha256": payload["payload_sha256"],
            "registry_report_sha256": sha256_file(work / REGISTRY_REPORT),
            "backend_receipts_sha256": sha256_file(work / BACKEND_RECEIPTS),
            "files": _registry_file_inventory(work),
        }
        manifest["manifest_sha256"] = _canonical_sha256(manifest)
        write_json(work / REGISTRY_MANIFEST, manifest)
        write_sha256s(work)
        integrity = verify_prospective_registry(work)
        if integrity.get("status") != "PASS":
            raise ValueError(
                "new registry receipt failed integrity verification: "
                + "; ".join(integrity.get("failures", []))
            )
        os.replace(work, output)

    return {
        "status": registration_status,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_id": payload["registry_id"],
        "registry_namespace": payload["registry_namespace"],
        "scoring_id": payload["scoring_id"],
        "payload_sha256": payload["payload_sha256"],
        "output": str(output),
        "source_scoring": str(scoring_root),
        "backend_receipts": receipts,
        "failures": failures,
        "integrity_status": "PASS",
    }


def _reject_symlinks(root: Path) -> list[str]:
    if root.is_symlink() or not root.is_dir():
        return [f"registry receipt is not a regular directory: {root}"]
    return [
        f"registry receipt contains symlink: {path.relative_to(root).as_posix()}"
        for path in root.rglob("*")
        if path.is_symlink()
    ]


def verify_prospective_registry(root: Path) -> dict[str, Any]:
    """Verify a registry receipt without contacting external backends."""

    root = root.resolve()
    failures = _reject_symlinks(root)
    failures.extend(f"SHA256SUMS:{item}" for item in verify_sha256s(root))
    try:
        payload = _read_json(root / REGISTRY_PAYLOAD, "registry payload")
        report = _read_json(root / REGISTRY_REPORT, "registry report")
        backend_receipt_payload = _read_json(
            root / BACKEND_RECEIPTS,
            "backend receipts",
        )
        receipts_value = backend_receipt_payload.get("receipts")
        if not isinstance(receipts_value, dict):
            raise ValueError("backend receipts.receipts must be an object")
        receipts = receipts_value
        manifest = _read_json(root / REGISTRY_MANIFEST, "registry manifest")
    except ValueError as exc:
        failures.append(str(exc))
        return {
            "status": "FAIL",
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "failures": failures,
        }

    payload_core = {
        key: value
        for key, value in payload.items()
        if key != "payload_sha256"
    }
    if payload.get("payload_sha256") != _canonical_sha256(payload_core):
        failures.append("registry payload canonical SHA-256 mismatch")
    manifest_core = {
        key: value
        for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    if manifest.get("manifest_sha256") != _canonical_sha256(manifest_core):
        failures.append("registry manifest canonical SHA-256 mismatch")
    if manifest.get("files") != _registry_file_inventory(root):
        failures.append("registry manifest file inventory mismatch")
    identities = {
        str(value)
        for value in (
            payload.get("registry_id"),
            report.get("registry_id"),
            manifest.get("registry_id"),
        )
        if str(value or "").strip()
    }
    if len(identities) != 1:
        failures.append("registry_id is missing or inconsistent")
    payload_shas = {
        str(value)
        for value in (
            payload.get("payload_sha256"),
            report.get("payload_sha256"),
            manifest.get("payload_sha256"),
        )
        if str(value or "").strip()
    }
    if len(payload_shas) != 1:
        failures.append("payload_sha256 is missing or inconsistent")
    if report.get("receipts") != receipts:
        failures.append("registry report receipts differ from backend receipts")
    attempted = backend_receipt_payload.get("attempted")
    if attempted != sorted(receipts):
        failures.append("backend receipt attempted list differs from receipt keys")
    if report.get("safety", {}).get("best_seed_only_selection") is not False:
        failures.append("best-seed-only selection safety flag must be false")
    if report.get("safety", {}).get("secrets_persisted") is not False:
        failures.append("registry safety must state that secrets were not persisted")
    if payload.get("metric_policy", {}).get("priority_metric") != "hit_pm1":
        failures.append("registry priority metric must be hit_pm1")
    if payload.get("metric_policy", {}).get("best_seed_only_selection") is not False:
        failures.append("registry metric policy permits best-seed-only selection")

    for item in report.get("source_evidence", []):
        if not isinstance(item, Mapping):
            failures.append("registry source evidence record is invalid")
            continue
        relative = Path(str(item.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            failures.append(f"unsafe registry source evidence path: {relative}")
            continue
        path = root / relative
        if path.is_symlink() or not path.is_file():
            failures.append(f"registry source evidence missing: {relative}")
            continue
        if sha256_file(path) != item.get("sha256"):
            failures.append(f"registry source evidence SHA mismatch: {relative}")
        if path.stat().st_size != item.get("size_bytes"):
            failures.append(f"registry source evidence size mismatch: {relative}")

    registration_status = str(report.get("status") or "")
    if registration_status == "PASS":
        required_receipts = {
            "postgres_prepare",
            "mlflow",
            "postgres_finalize",
        }
        if not required_receipts.issubset(receipts):
            failures.append("PASS registry receipt is missing required backend receipts")
        for name in sorted(required_receipts):
            if receipts.get(name, {}).get("status") != "PASS":
                failures.append(f"required backend receipt is not PASS: {name}")
        parent_id = receipts.get("mlflow", {}).get("parent_run_id")
        finalized_id = receipts.get("postgres_finalize", {}).get(
            "mlflow_parent_run_id"
        )
        if not parent_id or parent_id != finalized_id:
            failures.append("MLflow parent run differs from PostgreSQL finalization")
    elif registration_status != "BLOCKED":
        failures.append(f"unsupported registry operational status: {registration_status}")

    source_path = Path(str(payload.get("source", {}).get("scoring_root") or ""))
    source_reverification = "NOT_AVAILABLE"
    if source_path.is_dir():
        source_result = verify_prospective_scoring(source_path)
        source_reverification = str(source_result.get("status") or "FAIL")
        if source_reverification != "PASS":
            failures.append("current source scoring artifact verification failed")
        else:
            checks = {
                "SCORING_REPORT.json": payload["source"][
                    "scoring_report_sha256"
                ],
                "ARTIFACT_MANIFEST.json": payload["source"][
                    "artifact_manifest_sha256"
                ],
                "SHA256SUMS": payload["source"]["scoring_sha256s_sha256"],
                "ACTUALS_LOCK.json": payload["source"]["actuals_lock_sha256"],
            }
            for name, expected in checks.items():
                if sha256_file(source_path / name) != expected:
                    failures.append(f"current source scoring hash mismatch: {name}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_id": payload.get("registry_id"),
        "scoring_id": payload.get("scoring_id"),
        "registration_status": registration_status,
        "source_reverification": source_reverification,
        "failures": failures,
    }
