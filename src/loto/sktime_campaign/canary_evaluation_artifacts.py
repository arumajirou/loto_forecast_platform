from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.canary_evaluation import (
    CanaryEvaluationRequest,
    canonical_sha256,
    evaluate_shadow_canary,
    prediction_lock_payload,
)


class P10VerificationError(RuntimeError):
    """Raised when P10 evidence verification fails closed."""


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
        raise P10VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest_and_sha(output_dir: Path) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-p10-shadow-canary-evaluation",
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


def persist_p10(request: CanaryEvaluationRequest) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = evaluate_shadow_canary(request)
    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "stage": result["stage"],
        "run_id": request.run_id,
        "decision": result["decision"],
        "shadow_candidate_id": result["shadow_candidate_id"],
        "window_count": result["window_count"],
        "total_draws": result["total_draws"],
        "primary_promotion_eligible": result["primary_promotion_eligible"],
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
        "next_action": result["next_action"],
    }
    request_metadata = {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "evaluated_at_utc": request.evaluated_at_utc,
        "request_sha256": canonical_sha256(request.model_dump(mode="json")),
        "window_count": len(request.windows),
        "primary_promotion_executed": False,
    }
    window_evidence = [
        {
            "window": window.model_dump(mode="json"),
            "prediction_lock_payload": prediction_lock_payload(window),
            "prediction_lock_verification_status": "PASS",
        }
        for window in request.windows
    ]
    decision = {
        "schema_version": "1.0",
        "decision": result["decision"],
        "primary_promotion_eligible": result["primary_promotion_eligible"],
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "human_review_required": True,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
        "prediction_publication_allowed": False,
        "next_action": result["next_action"],
    }
    _write_json(output_dir / "REQUEST_METADATA.json", request_metadata)
    _write_json(output_dir / "P9_LINEAGE.json", request.p9.model_dump(mode="json"))
    _write_json(output_dir / "WINDOW_EVIDENCE.json", window_evidence)
    _write_json(output_dir / "WINDOW_METRICS.json", result["window_metrics"])
    _write_json(
        output_dir / "AGGREGATED_METRICS.json",
        {
            "per_series_metrics": result["per_series_metrics"],
            "candidate_metrics": result["candidate_metrics"],
        },
    )
    _write_json(
        output_dir / "BASELINE_COMPARISON.json",
        result["baseline_comparison"],
    )
    _write_json(output_dir / "RULE_EVALUATION.json", result["rule_evaluation"])
    _write_json(output_dir / "PRIMARY_PROMOTION_REVIEW_DECISION.json", decision)
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS":
        raise P10VerificationError("manifest status mismatch")
    if manifest.get("scope") != "sktime-p10-shadow-canary-evaluation":
        raise P10VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise P10VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P10VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P10VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P10VerificationError("manifest coverage mismatch")


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P10VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            expected, name = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise P10VerificationError("invalid SHA256SUMS line") from exc
        target = output_dir / name
        seen.add(name)
        if not target.is_file() or _sha256(target) != expected:
            raise P10VerificationError(f"SHA256SUMS mismatch: {name}")
    expected_names = {
        item.name for item in output_dir.iterdir() if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_names:
        raise P10VerificationError("SHA256SUMS coverage mismatch")


def verify_p10(request: CanaryEvaluationRequest, output_dir: Path) -> None:
    _verify_sha256sums(output_dir)
    _verify_manifest(output_dir)
    expected = evaluate_shadow_canary(request)
    response = _load_json(output_dir / "response.json")
    decision = _load_json(output_dir / "PRIMARY_PROMOTION_REVIEW_DECISION.json")
    window_evidence = _load_json(output_dir / "WINDOW_EVIDENCE.json")
    window_metrics = _load_json(output_dir / "WINDOW_METRICS.json")
    aggregate = _load_json(output_dir / "AGGREGATED_METRICS.json")
    comparison = _load_json(output_dir / "BASELINE_COMPARISON.json")
    rules = _load_json(output_dir / "RULE_EVALUATION.json")
    lineage = _load_json(output_dir / "P9_LINEAGE.json")
    if lineage != request.p9.model_dump(mode="json"):
        raise P10VerificationError("P9 lineage mismatch")
    if window_metrics != expected["window_metrics"]:
        raise P10VerificationError("window metrics mismatch")
    if aggregate != {
        "per_series_metrics": expected["per_series_metrics"],
        "candidate_metrics": expected["candidate_metrics"],
    }:
        raise P10VerificationError("aggregated metrics mismatch")
    if comparison != expected["baseline_comparison"]:
        raise P10VerificationError("baseline comparison mismatch")
    if rules != expected["rule_evaluation"]:
        raise P10VerificationError("rule evaluation mismatch")
    if response.get("decision") != expected["decision"]:
        raise P10VerificationError("response decision mismatch")
    if decision.get("decision") != expected["decision"]:
        raise P10VerificationError("formal decision mismatch")
    if response.get("primary_promotion_executed") is not False:
        raise P10VerificationError("response claims primary promotion")
    if response.get("primary_binding_changed") is not False:
        raise P10VerificationError("response claims primary binding change")
    if decision.get("human_review_required") is not True:
        raise P10VerificationError("human review boundary missing")
    expected_window_evidence = [
        {
            "window": window.model_dump(mode="json"),
            "prediction_lock_payload": prediction_lock_payload(window),
            "prediction_lock_verification_status": "PASS",
        }
        for window in request.windows
    ]
    if window_evidence != expected_window_evidence:
        raise P10VerificationError("window evidence mismatch")
