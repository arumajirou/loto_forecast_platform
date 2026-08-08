from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.registry_transaction import (
    FileRegistryState,
    P8RegistryTransactionRequest,
    commit_registry_transaction,
)


class P8VerificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
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
        raise P8VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _write_manifest(output_dir: Path) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-p8-file-registry-cas",
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


def _rollback_plan(result: dict[str, Any]) -> dict[str, Any]:
    record = result["history_record"]
    return {
        "schema_version": "1.0",
        "transaction_id": result["transaction_id"],
        "automatic_rollback": False,
        "rollback_status": "AVAILABLE_REQUIRES_NEW_P7_AUTHORIZATION",
        "rollback_expected_registry_state_sha256": result["post_state"]["state_sha256"],
        "rollback_target_binding": record.get("previous_binding"),
        "rollback_source_binding": record["new_binding"],
        "deployment_rollback_required": False,
        "reason": "P8 changes registry binding only and does not deploy the model",
    }


def persist_p8(
    request: P8RegistryTransactionRequest,
    *,
    committed_at_utc: str,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = commit_registry_transaction(request, committed_at_utc=committed_at_utc)
    metadata = {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "p7_bundle_sha256": request.p7_bundle_sha256,
        "registry_state_path": request.registry_state_path,
        "committed_at_utc": committed_at_utc,
        "automatic_deployment": False,
        "automatic_retraining": False,
    }
    p7_lineage = {
        "schema_version": "1.0",
        "p7_bundle_sha256": request.p7_bundle_sha256,
        "authorization_id": request.transaction.authorization_id,
        "authorization_seal_sha256": (request.transaction.authorization_seal_sha256),
        "authorization_expires_at_utc": request.authorization["expires_at_utc"],
        "approval_intent_sha256": request.authorization["approval_intent_sha256"],
    }
    plan = {
        "schema_version": "1.0",
        "backend": "file-json-cas-v1",
        "expected_registry_state_sha256": (request.transaction.expected_registry_state_sha256),
        "registry_target": request.transaction.subject.registry_target,
        "subject": request.transaction.subject.model_dump(mode="json"),
        "authorization_id": request.transaction.authorization_id,
        "transaction_nonce": request.transaction.transaction_nonce,
        "automatic_deployment": False,
    }
    consumption = {
        "schema_version": "1.0",
        "authorization_id": request.transaction.authorization_id,
        "transaction_nonce": request.transaction.transaction_nonce,
        "consumption_status": (
            "CONSUMED" if result["registry_write_executed"] else "ALREADY_CONSUMED_EXACT_REPLAY"
        ),
        "registry_generation": result["post_state"]["generation"],
        "transaction_id": result["transaction_id"],
    }
    receipt = {
        "schema_version": "1.0",
        "status": result["status"],
        "decision": result["decision"],
        "transaction_id": result["transaction_id"],
        "registry_write_executed": result["registry_write_executed"],
        "pre_state_sha256": result["pre_state"]["state_sha256"],
        "post_state_sha256": result["post_state"]["state_sha256"],
        "history_record": result["history_record"],
        "automatic_deployment": False,
        "deployment_status": "NOT_DEPLOYED",
        "promotion_status": "REGISTERED_NOT_DEPLOYED",
    }
    response = {
        "schema_version": "1.0",
        "status": "PASS",
        "operation": request.operation,
        "stage": "atomic_registry_compare_and_swap",
        "run_id": request.run_id,
        "decision": result["decision"],
        "transaction_id": result["transaction_id"],
        "registry_write_executed": result["registry_write_executed"],
        "authorization_consumed": True,
        "automatic_deployment": False,
        "deployment_status": "NOT_DEPLOYED",
        "automatic_retraining": False,
        "promotion_status": "REGISTERED_NOT_DEPLOYED",
        "next_action": "P9_EXTERNAL_REGISTRY_ADAPTER_OR_DEPLOYMENT_REVIEW",
    }
    _write_json(output_dir / "REQUEST_METADATA.json", metadata)
    _write_json(output_dir / "P7_LINEAGE.json", p7_lineage)
    _write_json(output_dir / "TRANSACTION_PLAN.json", plan)
    _write_json(output_dir / "PRE_REGISTRY_STATE.json", result["pre_state"])
    _write_json(output_dir / "TRANSACTION_RECEIPT.json", receipt)
    _write_json(output_dir / "POST_REGISTRY_STATE.json", result["post_state"])
    _write_json(output_dir / "AUTHORIZATION_CONSUMPTION.json", consumption)
    _write_json(output_dir / "ROLLBACK_PLAN.json", _rollback_plan(result))
    _write_json(output_dir / "response.json", response)
    _write_manifest(output_dir)
    return response


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != "PASS" or manifest.get("scope") != "sktime-p8-file-registry-cas":
        raise P8VerificationError("manifest identity mismatch")
    seen: set[str] = set()
    for item in manifest.get("files", []):
        name = str(item["path"])
        path = output_dir / name
        if name in seen or not path.is_file():
            raise P8VerificationError("manifest path mismatch")
        seen.add(name)
        if path.stat().st_size != int(item["size_bytes"]) or _sha256(path) != item["sha256"]:
            raise P8VerificationError(f"manifest mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P8VerificationError("manifest coverage mismatch")


def _verify_sha(output_dir: Path) -> None:
    seen: set[str] = set()
    for line in (output_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        if name in seen or _sha256(output_dir / name) != expected:
            raise P8VerificationError(f"SHA256SUMS mismatch: {name}")
        seen.add(name)
    expected = {
        path.name for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected:
        raise P8VerificationError("SHA256SUMS coverage mismatch")


def verify_p8(
    output_dir: Path,
    request: P8RegistryTransactionRequest,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    pre = FileRegistryState.model_validate(_load_json(output_dir / "PRE_REGISTRY_STATE.json"))
    post = FileRegistryState.model_validate(_load_json(output_dir / "POST_REGISTRY_STATE.json"))
    receipt = _load_json(output_dir / "TRANSACTION_RECEIPT.json")
    response = _load_json(output_dir / "response.json")
    plan = _load_json(output_dir / "TRANSACTION_PLAN.json")
    consumption = _load_json(output_dir / "AUTHORIZATION_CONSUMPTION.json")
    rollback = _load_json(output_dir / "ROLLBACK_PLAN.json")
    if plan["expected_registry_state_sha256"] != request.transaction.expected_registry_state_sha256:
        raise P8VerificationError("transaction plan expected-state mismatch")
    if (
        pre.state_sha256 != request.transaction.expected_registry_state_sha256
        and receipt["decision"] != "IDEMPOTENT_ALREADY_COMMITTED"
    ):
        raise P8VerificationError("pre-state does not match CAS expectation")
    if post.current_binding is None or post.current_binding.subject != request.transaction.subject:
        raise P8VerificationError("post-state binding differs from authorized subject")
    if request.transaction.authorization_id not in post.consumed_authorization_ids:
        raise P8VerificationError("authorization was not consumed")
    if request.transaction.transaction_nonce not in post.consumed_transaction_nonces:
        raise P8VerificationError("transaction nonce was not consumed")
    record = post.transaction_history[-1]
    if record.transaction_id != receipt["transaction_id"]:
        raise P8VerificationError("transaction receipt/history mismatch")
    if receipt["post_state_sha256"] != post.state_sha256:
        raise P8VerificationError("receipt post-state mismatch")
    if (
        response.get("automatic_deployment") is not False
        or response.get("deployment_status") != "NOT_DEPLOYED"
    ):
        raise P8VerificationError("P8 incorrectly deployed the model")
    if response.get("automatic_retraining") is not False:
        raise P8VerificationError("P8 enabled automatic retraining")
    if response.get("promotion_status") != "REGISTERED_NOT_DEPLOYED":
        raise P8VerificationError("P8 promotion status mismatch")
    if consumption.get("transaction_id") != record.transaction_id:
        raise P8VerificationError("authorization consumption mismatch")
    if rollback.get("automatic_rollback") is not False:
        raise P8VerificationError("automatic rollback was enabled")
    if rollback.get("rollback_expected_registry_state_sha256") != post.state_sha256:
        raise P8VerificationError("rollback expected-state mismatch")
    _verify_manifest(output_dir)
    _verify_sha(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p8-file-registry-cas",
        "decision": receipt["decision"],
        "transaction_id": receipt["transaction_id"],
        "registry_write_executed": receipt["registry_write_executed"],
        "authorization_consumed": True,
        "automatic_deployment": False,
        "deployment_status": "NOT_DEPLOYED",
        "promotion_status": "REGISTERED_NOT_DEPLOYED",
    }
