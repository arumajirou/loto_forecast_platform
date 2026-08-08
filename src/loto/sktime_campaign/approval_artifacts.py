from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.approval_authorization import (
    ApprovalAuthorizationRequest,
    SignatureVerifier,
    approval_intent_payload,
    canonical_sha256,
    issue_registry_authorization,
    verify_registry_authorization,
)


class P7VerificationError(RuntimeError):
    """Raised when P7 approval authorization evidence fails closed."""


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
        raise P7VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_metadata(
    request: ApprovalAuthorizationRequest,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "allowed_signers_sha256": request.allowed_signers_sha256,
        "approval_requested_at_utc": request.approval_requested_at_utc,
        "authorization_expires_at_utc": request.authorization_expires_at_utc,
        "authorization_nonce": request.authorization_nonce,
        "request_sha256": canonical_sha256(request.model_dump(mode="json")),
        "registry_write_executed": False,
    }


def _p6_lineage(request: ApprovalAuthorizationRequest) -> dict[str, Any]:
    return request.p6.model_dump(mode="json")


def _transaction_requirements(
    authorization: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": "register_model",
        "authorization_id": authorization["authorization_id"],
        "authorization_seal_sha256": authorization["seal_sha256"],
        "subject": authorization["subject"],
        "required_controls": [
            "authorization_not_expired",
            "authorization_not_consumed",
            "transaction_nonce_not_consumed",
            "subject_exact_match",
            "expected_registry_state_sha256_exact_match",
            "append_only_consumption_ledger",
            "compare_and_swap_registry_write",
        ],
        "registry_write_executed": False,
        "next_stage": "P8_COMPARE_AND_SWAP_REGISTRY_WRITE",
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
        "scope": "sktime-p7-manual-approval-authorization",
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


def persist_p7(
    request: ApprovalAuthorizationRequest,
    *,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = issue_registry_authorization(
        request,
        issued_at_utc=issued_at_utc,
        signature_verifier=signature_verifier,
    )
    authorization = result["authorization"]
    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "decision": result["decision"],
        "authorization_id": authorization["authorization_id"],
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
        "next_action": result["next_action"],
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(output_dir / "P6_LINEAGE.json", _p6_lineage(request))
    _write_json(
        output_dir / "APPROVAL_INTENT.json",
        approval_intent_payload(request),
    )
    _write_json(
        output_dir / "APPROVALS.json",
        [item.model_dump(mode="json") for item in request.approvals],
    )
    _write_json(
        output_dir / "SIGNATURE_VERIFICATION.json",
        result["signature_verification"],
    )
    _write_json(output_dir / "REGISTRY_AUTHORIZATION.json", authorization)
    _write_json(
        output_dir / "REGISTRY_TRANSACTION_REQUIREMENTS.json",
        _transaction_requirements(authorization),
    )
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS":
        raise P7VerificationError("manifest status mismatch")
    if manifest.get("scope") != "sktime-p7-manual-approval-authorization":
        raise P7VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise P7VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P7VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P7VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P7VerificationError("manifest coverage mismatch")


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P7VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            expected, name = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise P7VerificationError("malformed SHA256SUMS line") from exc
        if name in seen:
            raise P7VerificationError(f"duplicate SHA path: {name}")
        seen.add(name)
        artifact = output_dir / name
        if not artifact.is_file() or _sha256(artifact) != expected:
            raise P7VerificationError(f"SHA-256 mismatch: {name}")
    expected_files = {
        item.name for item in output_dir.iterdir() if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P7VerificationError("SHA256SUMS coverage mismatch")


def verify_p7(
    output_dir: Path,
    request: ApprovalAuthorizationRequest,
    *,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    expected = issue_registry_authorization(
        request,
        issued_at_utc=issued_at_utc,
        signature_verifier=signature_verifier,
    )
    authorization = expected["authorization"]
    verify_registry_authorization(authorization)
    if _load_json(output_dir / "REQUEST_METADATA.json") != _request_metadata(request):
        raise P7VerificationError("request metadata mismatch")
    if _load_json(output_dir / "P6_LINEAGE.json") != _p6_lineage(request):
        raise P7VerificationError("P6 lineage mismatch")
    if _load_json(output_dir / "APPROVAL_INTENT.json") != (approval_intent_payload(request)):
        raise P7VerificationError("approval intent mismatch")
    if _load_json(output_dir / "APPROVALS.json") != [
        item.model_dump(mode="json") for item in request.approvals
    ]:
        raise P7VerificationError("approval evidence mismatch")
    if _load_json(output_dir / "SIGNATURE_VERIFICATION.json") != expected["signature_verification"]:
        raise P7VerificationError("signature verification evidence mismatch")
    if _load_json(output_dir / "REGISTRY_AUTHORIZATION.json") != authorization:
        raise P7VerificationError("registry authorization mismatch")
    requirements = _transaction_requirements(authorization)
    if _load_json(output_dir / "REGISTRY_TRANSACTION_REQUIREMENTS.json") != (requirements):
        raise P7VerificationError("registry transaction requirements mismatch")
    response = _load_json(output_dir / "response.json")
    if response.get("status") != "PASS":
        raise P7VerificationError("P7 response status mismatch")
    if response.get("authorization_id") != authorization["authorization_id"]:
        raise P7VerificationError("P7 response authorization mismatch")
    if response.get("registry_write_authorized") is not True:
        raise P7VerificationError("P7 response did not authorize transaction")
    if response.get("registry_write_executed") is not False:
        raise P7VerificationError("P7 response incorrectly claims write")
    if response.get("automatic_promotion") is not False:
        raise P7VerificationError("P7 enabled automatic promotion")
    if response.get("automatic_retraining") is not False:
        raise P7VerificationError("P7 enabled automatic retraining")
    if response.get("promotion_status") != "APPROVED_NOT_REGISTERED":
        raise P7VerificationError("P7 response promotion status mismatch")
    _verify_manifest(output_dir)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p7-manual-approval-authorization",
        "authorization_id": authorization["authorization_id"],
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
