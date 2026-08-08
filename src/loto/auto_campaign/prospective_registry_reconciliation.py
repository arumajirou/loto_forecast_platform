"""Read-only reconciliation of local, PostgreSQL, and MLflow registry evidence."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .persistence import sha256_file, write_json, write_sha256s
from .prospective_registry import verify_prospective_registry
from .prospective_registry_contract import _canonical_sha256
from .prospective_registry_payload import _safe_error
from .prospective_registry_reconciliation_backends import (
    query_mlflow,
    query_postgres,
)
from .prospective_registry_reconciliation_comparison import (
    _compare_mlflow,
    _compare_postgres,
)
from .prospective_registry_reconciliation_contract import (
    MLFLOW_SNAPSHOT,
    POSTGRES_SNAPSHOT,
    RECONCILIATION_EXPECTED,
    RECONCILIATION_MANIFEST,
    RECONCILIATION_REPORT,
    RECONCILIATION_SCHEMA_VERSION,
    ReconciliationBackendFunctions,
    ReconciliationOptions,
)
from .prospective_registry_reconciliation_expected import (
    _copy_tree_exact,
    _expected_snapshot,
)
from .prospective_registry_reconciliation_verification import (
    _reconciliation_inventory,
    verify_registry_reconciliation,
)


def default_reconciliation_backends() -> ReconciliationBackendFunctions:
    return ReconciliationBackendFunctions(
        query_postgres=query_postgres,
        query_mlflow=query_mlflow,
    )


def reconcile_prospective_registry(
    *,
    receipt_root: Path,
    output: Path,
    options: ReconciliationOptions,
    backends: ReconciliationBackendFunctions | None = None,
) -> dict[str, Any]:
    """Compare immutable local receipt expectations with both live backends."""

    receipt_root = receipt_root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if output == receipt_root or receipt_root in output.parents:
        raise ValueError("reconciliation output must be outside the registry receipt")
    local = verify_prospective_registry(receipt_root)
    if local.get("status") != "PASS":
        raise ValueError(
            "registry receipt verification failed: " + "; ".join(local.get("failures", []))
        )
    expected = _expected_snapshot(receipt_root)
    backend_policy = expected["backend_policy"]
    postgres_env = options.postgres_dsn_env or backend_policy["postgres_dsn_env"]
    mlflow_env = options.mlflow_uri_env or backend_policy["mlflow_uri_env"]
    dsn = os.getenv(postgres_env, "")
    mlflow_uri = options.mlflow_uri or os.getenv(mlflow_env, "")
    backend_functions = backends or default_reconciliation_backends()
    failures: list[str] = []
    backend_errors: list[dict[str, Any]] = []
    postgres_snapshot: dict[str, Any]
    mlflow_snapshot: dict[str, Any]

    if not dsn:
        postgres_snapshot = {
            "backend": "postgres",
            "status": "BLOCKED",
            "error": f"PostgreSQL DSN is missing; set {postgres_env}",
        }
        backend_errors.append(dict(postgres_snapshot))
    else:
        try:
            postgres_snapshot = backend_functions.query_postgres(dsn, expected)
        except Exception as exc:  # noqa: BLE001
            postgres_snapshot = {
                "backend": "postgres",
                "status": "BLOCKED",
                **_safe_error(
                    exc,
                    secrets=(dsn, mlflow_uri),
                    phase="POSTGRES_QUERY",
                ),
            }
            backend_errors.append(dict(postgres_snapshot))

    if not mlflow_uri:
        mlflow_snapshot = {
            "backend": "mlflow",
            "status": "BLOCKED",
            "error": f"MLflow URI is missing; set {mlflow_env}",
        }
        backend_errors.append(dict(mlflow_snapshot))
    else:
        try:
            mlflow_snapshot = backend_functions.query_mlflow(
                mlflow_uri,
                backend_policy["mlflow_experiment"],
                expected,
                require_remote_artifacts=options.require_remote_artifacts,
            )
        except Exception as exc:  # noqa: BLE001
            mlflow_snapshot = {
                "backend": "mlflow",
                "status": "BLOCKED",
                **_safe_error(
                    exc,
                    secrets=(dsn, mlflow_uri),
                    phase="MLFLOW_QUERY",
                ),
            }
            backend_errors.append(dict(mlflow_snapshot))

    if not backend_errors:
        failures.extend(
            _compare_postgres(
                expected,
                postgres_snapshot,
                options.float_tolerance,
            )
        )
        failures.extend(
            _compare_mlflow(
                expected,
                mlflow_snapshot,
                options.float_tolerance,
                require_remote_artifacts=options.require_remote_artifacts,
            )
        )
        postgres_runs = postgres_snapshot.get("run_rows") or []
        mlflow_parents = mlflow_snapshot.get("parent_runs") or []
        if len(postgres_runs) == 1 and len(mlflow_parents) == 1:
            if postgres_runs[0].get("mlflow_parent_run_id") != mlflow_parents[0].get("run_id"):
                failures.append("PostgreSQL and MLflow disagree on parent run ID")

    status = "BLOCKED" if backend_errors else "DRIFT" if failures else "PASS"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="registry-reconciliation-",
        dir=output.parent,
    ) as temp:
        work = Path(temp) / "artifact"
        work.mkdir()
        copied_receipt = _copy_tree_exact(
            receipt_root,
            work / "source_receipt",
        )
        write_json(work / RECONCILIATION_EXPECTED, expected)
        write_json(work / POSTGRES_SNAPSHOT, postgres_snapshot)
        write_json(work / MLFLOW_SNAPSHOT, mlflow_snapshot)
        report = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "status": status,
            "registry_id": expected["registry_id"],
            "scoring_id": expected["scoring_id"],
            "payload_sha256": expected["payload_sha256"],
            "reconciled_at": datetime.now(UTC).isoformat(),
            "source_receipt_verification": "PASS",
            "required_backends": ["postgres", "mlflow"],
            "float_tolerance": options.float_tolerance,
            "require_remote_artifacts": options.require_remote_artifacts,
            "postgres_status": postgres_snapshot.get("status"),
            "mlflow_status": mlflow_snapshot.get("status"),
            "drift_failures": failures,
            "backend_errors": backend_errors,
            "source_receipt": copied_receipt,
            "safety": {
                "read_only_backend_access": True,
                "automatic_repair": False,
                "automatic_promotion": False,
                "automatic_retraining": False,
                "secrets_persisted": False,
            },
        }
        write_json(work / RECONCILIATION_REPORT, report)
        manifest: dict[str, Any] = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "status": status,
            "registry_id": expected["registry_id"],
            "scoring_id": expected["scoring_id"],
            "payload_sha256": expected["payload_sha256"],
            "expected_sha256": sha256_file(work / RECONCILIATION_EXPECTED),
            "postgres_snapshot_sha256": sha256_file(work / POSTGRES_SNAPSHOT),
            "mlflow_snapshot_sha256": sha256_file(work / MLFLOW_SNAPSHOT),
            "report_sha256": sha256_file(work / RECONCILIATION_REPORT),
            "files": _reconciliation_inventory(work),
        }
        manifest["manifest_sha256"] = _canonical_sha256(manifest)
        write_json(work / RECONCILIATION_MANIFEST, manifest)
        write_sha256s(work)
        integrity = verify_registry_reconciliation(work)
        if integrity.get("status") != "PASS":
            raise ValueError(
                "new reconciliation artifact failed integrity verification: "
                + "; ".join(integrity.get("failures", []))
            )
        os.replace(work, output)
    return {
        "status": status,
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "registry_id": expected["registry_id"],
        "scoring_id": expected["scoring_id"],
        "output": str(output),
        "drift_failures": failures,
        "backend_errors": backend_errors,
        "integrity_status": "PASS",
    }
