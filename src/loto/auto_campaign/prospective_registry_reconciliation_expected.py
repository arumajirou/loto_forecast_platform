"""Build immutable expectations from a verified registry receipt."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .persistence import sha256_file
from .prospective_registry_contract import (
    BACKEND_RECEIPTS,
    REGISTRY_PAYLOAD,
    REGISTRY_REPORT,
    _canonical_sha256,
    _read_json,
)
from .prospective_registry_payload import (
    _candidate_frame,
    _position_metric_frame,
    _read_registry_tables,
    _seed_metric_frame,
)
from .prospective_registry_reconciliation_contract import RECONCILIATION_SCHEMA_VERSION


def _copy_tree_exact(source: Path, target: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"registry receipt must be a regular directory: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                f"registry receipt contains a symlink: {path.relative_to(source).as_posix()}"
            )
    shutil.copytree(source, target)
    source_files = {
        path.relative_to(source).as_posix(): sha256_file(path)
        for path in source.rglob("*")
        if path.is_file()
    }
    target_files = {
        path.relative_to(target).as_posix(): sha256_file(path)
        for path in target.rglob("*")
        if path.is_file()
    }
    if source_files != target_files:
        raise RuntimeError("registry receipt copy differs from source")
    return {
        "path": target.name,
        "file_count": len(target_files),
        "tree_sha256": _canonical_sha256(target_files),
    }


def _expected_artifacts(receipt_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    scoring_manifest = _read_json(
        receipt_root / "source_evidence" / "ARTIFACT_MANIFEST.json",
        "copied scoring artifact manifest",
    )
    records = scoring_manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("copied scoring artifact manifest file inventory is missing")
    rows: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("copied scoring artifact inventory record is invalid")
        path = str(item.get("path") or "")
        rows[path] = {
            "registry_id": payload["registry_id"],
            "path": path,
            "size_bytes": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
        }
    for name in (
        "ARTIFACT_MANIFEST.json",
        "SCORING_REPORT.json",
        "ACTUALS_LOCK.json",
        "SHA256SUMS",
    ):
        source = receipt_root / "source_evidence" / name
        rows[name] = {
            "registry_id": payload["registry_id"],
            "path": name,
            "size_bytes": source.stat().st_size,
            "sha256": sha256_file(source),
        }
    return [rows[name] for name in sorted(rows)]


def _expected_snapshot(receipt_root: Path) -> dict[str, Any]:
    payload = _read_json(receipt_root / REGISTRY_PAYLOAD, "registry payload")
    report = _read_json(receipt_root / REGISTRY_REPORT, "registry report")
    backend_receipts = _read_json(
        receipt_root / BACKEND_RECEIPTS,
        "backend receipts",
    )
    receipts = backend_receipts.get("receipts")
    if not isinstance(receipts, dict):
        raise ValueError("backend receipts.receipts must be an object")
    if report.get("status") != "PASS":
        raise ValueError("only PASS registry receipts can be formally reconciled")
    tables = _read_registry_tables(receipt_root / "source_evidence")
    registry_id = str(payload["registry_id"])
    candidates = _candidate_frame(
        tables["seed_summary"],
        tables["ranking"],
        registry_id,
    )
    seed_metrics = _seed_metric_frame(
        tables["seed_metrics"],
        registry_id,
    )
    position_metrics = _position_metric_frame(
        tables["position_metrics"],
        registry_id,
    )
    artifacts = pd.DataFrame(_expected_artifacts(receipt_root, payload))
    mlflow_receipt = receipts.get("mlflow")
    postgres_finalize = receipts.get("postgres_finalize")
    if not isinstance(mlflow_receipt, dict) or not isinstance(postgres_finalize, dict):
        raise ValueError("PASS registry receipt lacks finalized backend receipts")
    parent_run_id = str(mlflow_receipt.get("parent_run_id") or "")
    if not parent_run_id:
        raise ValueError("MLflow parent run ID is missing from registry receipt")
    if postgres_finalize.get("mlflow_parent_run_id") != parent_run_id:
        raise ValueError("receipt PostgreSQL and MLflow parent run IDs differ")
    backend_policy = payload.get("backend_policy")
    if not isinstance(backend_policy, dict):
        raise ValueError("registry payload backend policy is missing")
    mlflow_artifacts = [
        {
            "path": "registry_evidence/REGISTRY_PAYLOAD.json",
            "sha256": sha256_file(receipt_root / REGISTRY_PAYLOAD),
        },
        {
            "path": ("registry_evidence/source_evidence/ARTIFACT_MANIFEST.json"),
            "sha256": sha256_file(receipt_root / "source_evidence" / "ARTIFACT_MANIFEST.json"),
        },
    ]
    if backend_policy.get("artifact_mode") == "full":
        mlflow_artifacts.append(
            {
                "path": "scoring_artifact/SCORING_REPORT.json",
                "sha256": sha256_file(receipt_root / "source_evidence" / "SCORING_REPORT.json"),
            }
        )
    expected = {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "registry_id": registry_id,
        "registry_namespace": payload["registry_namespace"],
        "scoring_id": payload["scoring_id"],
        "payload_sha256": payload["payload_sha256"],
        "created_at": payload["created_at"],
        "source": payload["source"],
        "counts": payload["counts"],
        "backend_policy": backend_policy,
        "receipt_mlflow_parent_run_id": parent_run_id,
        "candidates": candidates.to_dict(orient="records"),
        "seed_metrics": seed_metrics.to_dict(orient="records"),
        "position_metrics": position_metrics.to_dict(orient="records"),
        "artifacts": artifacts.to_dict(orient="records"),
        "mlflow_artifacts": mlflow_artifacts,
    }
    expected["expected_sha256"] = _canonical_sha256(expected)
    return expected
