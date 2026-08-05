from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.deployment_canary import (
    CanaryActivationRequest,
    activate_shadow_canary,
    canonical_sha256,
)


class P9VerificationError(RuntimeError):
    """Raised when P9 shadow-canary evidence fails verification."""


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
        raise P9VerificationError(f"unable to read JSON {path}: {exc}") from exc


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
        if path.is_file()
        and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-p9-shadow-canary-activation",
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
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    _atomic_write_text(
        output_dir / "SHA256SUMS",
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hashed) + "\n",
    )


def persist_p9(
    request: CanaryActivationRequest,
    *,
    committed_at_utc: str,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = activate_shadow_canary(request, committed_at_utc=committed_at_utc)
    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": request.operation,
        "run_id": request.run_id,
        "decision": result["decision"],
        "activation_id": result["activation_id"],
        "deployment_state_changed": result["deployment_state_changed"],
        "primary_binding_unchanged": True,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
        "promotion_status": "CANARY_ACTIVE_NOT_PRIMARY",
        "next_action": "P10_SCORE_SHADOW_CANARY_DRAWS",
    }
    plan = {
        "schema_version": "1.0",
        "deployment_target": request.deployment_target,
        "expected_deployment_state_sha256": (
            request.expected_deployment_state_sha256
        ),
        "activation_nonce": request.activation_nonce,
        "subject": request.p8.subject.model_dump(mode="json"),
        "policy": request.policy.model_dump(mode="json"),
        "request_sha256": canonical_sha256(request.model_dump(mode="json")),
    }
    receipt = {
        "schema_version": "1.0",
        "decision": result["decision"],
        "activation_id": result["activation_id"],
        "deployment_state_changed": result["deployment_state_changed"],
        "pre_state_sha256": result["pre_state"]["state_sha256"],
        "post_state_sha256": result["post_state"]["state_sha256"],
        "primary_binding_unchanged": True,
        "prediction_publication_allowed": False,
        "receipt_sha256": "",
    }
    receipt["receipt_sha256"] = canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    rollback = {
        "schema_version": "1.0",
        "automatic_rollback": False,
        "rollback_executed": False,
        "previous_primary": result["pre_state"]["primary_binding"],
        "previous_canary": result["pre_state"]["canary_binding"],
        "current_canary": result["post_state"]["canary_binding"],
        "required_action": "NEW_REVIEW_AND_CAS_TRANSACTION",
    }
    _write_json(
        output_dir / "REQUEST_METADATA.json",
        {
            "schema_version": "1.0",
            "run_id": request.run_id,
            "git_commit": request.git_commit,
            "code_sha256": request.code_sha256,
            "config_sha256": request.config_sha256,
            "requested_at_utc": request.requested_at_utc,
            "request_sha256": canonical_sha256(request.model_dump(mode="json")),
        },
    )
    _write_json(output_dir / "P8_LINEAGE.json", request.p8.model_dump(mode="json"))
    _write_json(
        output_dir / "RUNTIME_PROBE.json",
        request.runtime_probe.model_dump(mode="json"),
    )
    _write_json(output_dir / "ACTIVATION_PLAN.json", plan)
    _write_json(output_dir / "PRE_DEPLOYMENT_STATE.json", result["pre_state"])
    _write_json(output_dir / "ACTIVATION_RECEIPT.json", receipt)
    _write_json(output_dir / "POST_DEPLOYMENT_STATE.json", result["post_state"])
    _write_json(output_dir / "ROLLBACK_PLAN.json", rollback)
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS":
        raise P9VerificationError("manifest status mismatch")
    if manifest.get("scope") != "sktime-p9-shadow-canary-activation":
        raise P9VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise P9VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P9VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P9VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P9VerificationError("manifest coverage mismatch")


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P9VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        artifact = output_dir / name
        if name in seen or not artifact.is_file() or _sha256(artifact) != expected:
            raise P9VerificationError(f"SHA-256 mismatch: {name}")
        seen.add(name)
    expected_files = {
        item.name
        for item in output_dir.iterdir()
        if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P9VerificationError("SHA256SUMS coverage mismatch")


def verify_p9(output_dir: Path, request: CanaryActivationRequest) -> dict[str, Any]:
    response = _load_json(output_dir / "response.json")
    if response.get("status") != "PASS":
        raise P9VerificationError("P9 response status mismatch")
    if response.get("primary_binding_unchanged") is not True:
        raise P9VerificationError("P9 changed the primary binding")
    if response.get("prediction_publication_allowed") is not False:
        raise P9VerificationError("P9 enabled prediction publication")
    if response.get("automatic_primary_promotion") is not False:
        raise P9VerificationError("P9 enabled automatic primary promotion")
    if response.get("promotion_status") != "CANARY_ACTIVE_NOT_PRIMARY":
        raise P9VerificationError("P9 promotion status mismatch")
    if _load_json(output_dir / "P8_LINEAGE.json") != request.p8.model_dump(
        mode="json"
    ):
        raise P9VerificationError("P8 lineage mismatch")
    if _load_json(output_dir / "RUNTIME_PROBE.json") != (
        request.runtime_probe.model_dump(mode="json")
    ):
        raise P9VerificationError("runtime probe mismatch")
    pre_state = _load_json(output_dir / "PRE_DEPLOYMENT_STATE.json")
    post_state = _load_json(output_dir / "POST_DEPLOYMENT_STATE.json")
    if pre_state["primary_binding"] != post_state["primary_binding"]:
        raise P9VerificationError("primary binding changed")
    if post_state["canary_binding"] is None:
        raise P9VerificationError("canary binding was not activated")
    if post_state["canary_binding"]["subject"] != request.p8.subject.model_dump(
        mode="json"
    ):
        raise P9VerificationError("canary subject mismatch")
    receipt = _load_json(output_dir / "ACTIVATION_RECEIPT.json")
    receipt_payload = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    if receipt.get("receipt_sha256") != canonical_sha256(receipt_payload):
        raise P9VerificationError("activation receipt seal mismatch")
    if receipt.get("pre_state_sha256") != pre_state["state_sha256"]:
        raise P9VerificationError("receipt pre-state mismatch")
    if receipt.get("post_state_sha256") != post_state["state_sha256"]:
        raise P9VerificationError("receipt post-state mismatch")
    _verify_manifest(output_dir)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p9-shadow-canary-activation",
        "decision": response["decision"],
        "promotion_status": "CANARY_ACTIVE_NOT_PRIMARY",
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
    }
