from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.promotion_gate import (
    PromotionGateRequest,
    canonical_sha256,
    run_promotion_gate,
)


class P6VerificationError(RuntimeError):
    """Raised when P6 promotion-gate evidence fails closed verification."""


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
        raise P6VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_metadata(request: PromotionGateRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "shadow_candidate_id": request.shadow_candidate_id,
        "runtime_certification_status": request.runtime_certification_status,
        "leakage_audit_status": request.leakage_audit_status,
        "data_quality_status": request.data_quality_status,
        "seed_policy_status": request.seed_policy_status,
        "preactual_lock_status": request.preactual_lock_status,
        "policy": request.policy.model_dump(mode="json"),
        "human_approval_granted": False,
        "request_sha256": canonical_sha256(request.model_dump(mode="json")),
    }


def _upstream_lineage(request: PromotionGateRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "upstream_artifact_sha256": request.upstream_artifact_sha256,
        "p5_monitor_bundle_sha256": [item.monitor_bundle_sha256 for item in request.windows],
        "prediction_lock_seal_sha256": [
            item.prediction_lock_seal_sha256 for item in request.windows
        ],
        "actuals_source_sha256": [item.actuals_source_sha256 for item in request.windows],
    }


def _write_manifest_and_sha(output_dir: Path) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-p6-manual-promotion-gate",
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    _write_json(output_dir / "ARTIFACT_MANIFEST.json", manifest)
    hashed = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    _atomic_write_text(
        output_dir / "SHA256SUMS",
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hashed) + "\n",
    )


def persist_p6(request: PromotionGateRequest) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = run_promotion_gate(request)
    decision = {
        "schema_version": "1.0",
        "shadow_candidate_id": result["shadow_candidate_id"],
        "decision": result["decision"],
        "eligible_for_human_approval": result["eligible_for_human_approval"],
        "human_approval_required": True,
        "human_approval_granted": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
        "next_action": result["next_action"],
    }
    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "shadow_candidate_id": request.shadow_candidate_id,
        "window_count": result["aggregated_metrics"]["window_count"],
        "total_draw_count": result["aggregated_metrics"]["total_draw_count"],
        "decision": result["decision"],
        "eligible_for_human_approval": result["eligible_for_human_approval"],
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "NOT_PROMOTED",
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(output_dir / "UPSTREAM_LINEAGE.json", _upstream_lineage(request))
    _write_json(
        output_dir / "WINDOW_EVIDENCE.json",
        [item.model_dump(mode="json") for item in request.windows],
    )
    _write_json(
        output_dir / "AGGREGATED_METRICS.json",
        result["aggregated_metrics"],
    )
    _write_json(
        output_dir / "RULE_EVALUATION.json",
        result["rule_evaluation"],
    )
    _write_json(output_dir / "PROMOTION_DECISION.json", decision)
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS":
        raise P6VerificationError("manifest status mismatch")
    if manifest.get("scope") != "sktime-p6-manual-promotion-gate":
        raise P6VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise P6VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P6VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P6VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P6VerificationError("manifest coverage mismatch")


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P6VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        if name in seen:
            raise P6VerificationError(f"duplicate SHA path: {name}")
        seen.add(name)
        artifact = output_dir / name
        if not artifact.is_file() or _sha256(artifact) != expected:
            raise P6VerificationError(f"SHA-256 mismatch: {name}")
    expected_files = {
        item.name for item in output_dir.iterdir() if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P6VerificationError("SHA256SUMS coverage mismatch")


def verify_p6(
    output_dir: Path,
    request: PromotionGateRequest,
) -> dict[str, Any]:
    expected = run_promotion_gate(request)
    if _load_json(output_dir / "REQUEST_METADATA.json") != _request_metadata(request):
        raise P6VerificationError("request metadata mismatch")
    if _load_json(output_dir / "UPSTREAM_LINEAGE.json") != _upstream_lineage(request):
        raise P6VerificationError("upstream lineage mismatch")
    if _load_json(output_dir / "WINDOW_EVIDENCE.json") != [
        item.model_dump(mode="json") for item in request.windows
    ]:
        raise P6VerificationError("window evidence mismatch")
    if _load_json(output_dir / "AGGREGATED_METRICS.json") != expected["aggregated_metrics"]:
        raise P6VerificationError("aggregated metrics mismatch")
    if _load_json(output_dir / "RULE_EVALUATION.json") != expected["rule_evaluation"]:
        raise P6VerificationError("rule evaluation mismatch")
    decision = _load_json(output_dir / "PROMOTION_DECISION.json")
    if decision.get("decision") != expected["decision"]:
        raise P6VerificationError("promotion decision mismatch")
    if decision.get("automatic_promotion") is not False:
        raise P6VerificationError("automatic promotion was enabled")
    if decision.get("automatic_retraining") is not False:
        raise P6VerificationError("automatic retraining was enabled")
    if decision.get("registry_write_allowed") is not False:
        raise P6VerificationError("registry write was enabled")
    if decision.get("promotion_status") != "NOT_PROMOTED":
        raise P6VerificationError("P6 incorrectly claims promotion")
    response = _load_json(output_dir / "response.json")
    if response.get("status") != "PASS":
        raise P6VerificationError("P6 integrity status mismatch")
    if response.get("decision") != expected["decision"]:
        raise P6VerificationError("P6 response decision mismatch")
    if response.get("promotion_status") != "NOT_PROMOTED":
        raise P6VerificationError("P6 response incorrectly claims promotion")
    _verify_manifest(output_dir)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p6-manual-promotion-gate",
        "decision": expected["decision"],
        "eligible_for_human_approval": expected["eligible_for_human_approval"],
        "automatic_promotion": False,
        "automatic_retraining": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
    }
