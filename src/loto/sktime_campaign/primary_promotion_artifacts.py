from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.primary_promotion_authorization import (
    PrimaryPromotionAuthorizationRequest,
    SignatureVerifier,
    canonical_sha256,
    issue_primary_promotion_authorization,
    primary_promotion_intent,
    verify_authorization_seal,
)


class P11VerificationError(RuntimeError):
    """Raised when P11 primary-promotion authorization evidence fails."""


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
        raise P11VerificationError(f"unable to read JSON {path}: {exc}") from exc


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
        "scope": "sktime-p11-primary-promotion-authorization",
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


def persist_p11(
    request: PrimaryPromotionAuthorizationRequest,
    *,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = issue_primary_promotion_authorization(
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
        "primary_promotion_authorized": True,
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "canary_binding_changed": False,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
        "promotion_status": "APPROVED_NOT_PRIMARY",
        "next_action": result["next_action"],
    }
    requirements = {
        "schema_version": "1.0",
        "next_stage": "P12_ATOMIC_PRIMARY_PROMOTION_TRANSACTION",
        "authorization_id": authorization["authorization_id"],
        "authorization_seal_sha256": authorization["seal_sha256"],
        "deployment_target": authorization["deployment_target"],
        "expected_deployment_state_sha256": (
            authorization["expected_deployment_state_sha256"]
        ),
        "expected_primary_before": authorization["expected_primary_before"],
        "expected_canary_before": authorization["expected_canary_before"],
        "target_primary": authorization["target_primary"],
        "clear_canary_on_commit": True,
        "required_controls": [
            "authorization_not_expired",
            "authorization_not_consumed",
            "transaction_nonce_not_consumed",
            "deployment_state_compare_and_swap",
            "primary_exact_match",
            "canary_exact_match",
            "target_primary_exact_match",
            "append_only_consumption_ledger",
            "atomic_primary_and_canary_update",
            "post_write_state_verification",
        ],
        "primary_promotion_executed": False,
    }
    rollback = {
        "schema_version": "1.0",
        "rollback_target": authorization["rollback_target"],
        "monitoring": authorization["monitoring"],
        "automatic_rollback": False,
        "rollback_executed": False,
        "rollback_requires_new_authorization": True,
        "required_action": "NEW_P10_REVIEW_AND_P11_P12_TRANSACTION",
    }
    _write_json(
        output_dir / "REQUEST_METADATA.json",
        {
            "schema_version": "1.0",
            "run_id": request.run_id,
            "git_commit": request.git_commit,
            "code_sha256": request.code_sha256,
            "config_sha256": request.config_sha256,
            "allowed_signers_sha256": request.allowed_signers_sha256,
            "requested_at_utc": request.requested_at_utc,
            "expires_at_utc": request.expires_at_utc,
            "request_sha256": canonical_sha256(request.model_dump(mode="json")),
        },
    )
    _write_json(output_dir / "P10_LINEAGE.json", request.p10.model_dump(mode="json"))
    _write_json(
        output_dir / "DEPLOYMENT_PRECONDITION.json",
        request.deployment.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "PRIMARY_PROMOTION_INTENT.json",
        primary_promotion_intent(request),
    )
    _write_json(
        output_dir / "APPROVALS.json",
        [item.model_dump(mode="json") for item in request.approvals],
    )
    _write_json(
        output_dir / "SIGNATURE_VERIFICATION.json",
        result["signature_verification"],
    )
    _write_json(
        output_dir / "PRIMARY_PROMOTION_AUTHORIZATION.json",
        authorization,
    )
    _write_json(
        output_dir / "P12_TRANSACTION_REQUIREMENTS.json",
        requirements,
    )
    _write_json(
        output_dir / "ROLLBACK_AND_MONITORING_PLAN.json",
        rollback,
    )
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS":
        raise P11VerificationError("manifest status mismatch")
    if manifest.get("scope") != (
        "sktime-p11-primary-promotion-authorization"
    ):
        raise P11VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise P11VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P11VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P11VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P11VerificationError("manifest coverage mismatch")


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P11VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            expected, name = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise P11VerificationError("invalid SHA256SUMS line") from exc
        artifact = output_dir / name
        if name in seen or not artifact.is_file() or _sha256(artifact) != expected:
            raise P11VerificationError(f"SHA-256 mismatch: {name}")
        seen.add(name)
    expected_files = {
        item.name
        for item in output_dir.iterdir()
        if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P11VerificationError("SHA256SUMS coverage mismatch")


def verify_p11(
    output_dir: Path,
    request: PrimaryPromotionAuthorizationRequest,
) -> dict[str, Any]:
    response = _load_json(output_dir / "response.json")
    if response.get("status") != "PASS":
        raise P11VerificationError("P11 response status mismatch")
    if response.get("decision") != (
        "AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION"
    ):
        raise P11VerificationError("P11 decision mismatch")
    if response.get("primary_promotion_authorized") is not True:
        raise P11VerificationError("P11 did not authorize promotion")
    for field in (
        "primary_promotion_executed",
        "primary_binding_changed",
        "canary_binding_changed",
        "prediction_publication_allowed",
        "automatic_primary_promotion",
        "automatic_retraining",
        "automatic_rollback",
    ):
        if response.get(field) is not False:
            raise P11VerificationError(f"P11 changed forbidden field: {field}")
    if response.get("promotion_status") != "APPROVED_NOT_PRIMARY":
        raise P11VerificationError("P11 promotion status mismatch")
    if _load_json(output_dir / "P10_LINEAGE.json") != request.p10.model_dump(
        mode="json"
    ):
        raise P11VerificationError("P10 lineage mismatch")
    if _load_json(output_dir / "DEPLOYMENT_PRECONDITION.json") != (
        request.deployment.model_dump(mode="json")
    ):
        raise P11VerificationError("deployment precondition mismatch")
    intent = _load_json(output_dir / "PRIMARY_PROMOTION_INTENT.json")
    if intent != primary_promotion_intent(request):
        raise P11VerificationError("primary promotion intent mismatch")
    approvals = _load_json(output_dir / "APPROVALS.json")
    expected_approvals = [
        item.model_dump(mode="json") for item in request.approvals
    ]
    if approvals != expected_approvals:
        raise P11VerificationError("approvals mismatch")
    verification = _load_json(output_dir / "SIGNATURE_VERIFICATION.json")
    if len(verification) != 3 or not all(
        item.get("verified") is True for item in verification
    ):
        raise P11VerificationError("signature verification evidence mismatch")
    authorization = _load_json(
        output_dir / "PRIMARY_PROMOTION_AUTHORIZATION.json"
    )
    try:
        verify_authorization_seal(authorization)
    except ValueError as exc:
        raise P11VerificationError(str(exc)) from exc
    if authorization.get("intent_sha256") != canonical_sha256(intent):
        raise P11VerificationError("authorization intent mismatch")
    if authorization.get("expected_deployment_state_sha256") != (
        request.deployment.deployment_state_sha256
    ):
        raise P11VerificationError("authorization deployment state mismatch")
    if authorization.get("target_primary") != intent["target_primary"]:
        raise P11VerificationError("authorization target primary mismatch")
    requirements = _load_json(output_dir / "P12_TRANSACTION_REQUIREMENTS.json")
    if requirements.get("authorization_id") != authorization["authorization_id"]:
        raise P11VerificationError("P12 authorization ID mismatch")
    if requirements.get("authorization_seal_sha256") != authorization["seal_sha256"]:
        raise P11VerificationError("P12 authorization seal mismatch")
    rollback = _load_json(output_dir / "ROLLBACK_AND_MONITORING_PLAN.json")
    if rollback.get("rollback_target") != authorization["rollback_target"]:
        raise P11VerificationError("rollback target mismatch")
    if rollback.get("automatic_rollback") is not False:
        raise P11VerificationError("automatic rollback was enabled")
    _verify_manifest(output_dir)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": (
            "sktime-p11-primary-promotion-authorization"
        ),
        "decision": response["decision"],
        "promotion_status": "APPROVED_NOT_PRIMARY",
        "primary_promotion_executed": False,
    }
