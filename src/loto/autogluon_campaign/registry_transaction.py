from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loto.autogluon_campaign.approval_authorization_contract import (
    RegistrySubject,
    SignatureVerifier,
    canonical_sha256,
    verify_registry_authorization,
)
from loto.autogluon_campaign.approval_authorization_io import load_json, tree_sha256
from loto.autogluon_campaign.registry_transaction_contract import (
    BACKEND,
    P19_SCHEMA,
    RegistryHistoryRecord,
    RegistryState,
    RegistryTransactionError,
    RegistryTransactionRequest,
    RegistryTransactionResult,
    authorization_is_expired,
    make_history_record,
    make_registry_state,
    transaction_identity,
    validate_registry_target_matches_path,
)
from loto.autogluon_campaign.registry_transaction_io import (
    load_registry_state,
    read_p18_authorization,
    registry_lock,
    transaction_output_tree_sha256,
    validate_registry_path,
    verify_transaction_evidence_files,
    write_transaction_evidence,
    atomic_write_registry_state,
)


def _assert_output_available(output_dir: Path, source_dir: Path) -> Path:
    output = output_dir.resolve(strict=False)
    source = source_dir.resolve()
    if output == source or source in output.parents:
        raise RegistryTransactionError("OUTPUT_INSIDE_P18_SOURCE", str(output))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RegistryTransactionError("OUTPUT_NOT_EMPTY", str(output))
    return output


def _matching_history_record(
    state: RegistryState,
    *,
    authorization_id: str,
    transaction_nonce: str,
) -> RegistryHistoryRecord | None:
    authorization_rows = [
        row for row in state.history if row.authorization_id == authorization_id
    ]
    nonce_rows = [row for row in state.history if row.transaction_nonce == transaction_nonce]
    if not authorization_rows and not nonce_rows:
        return None
    if len(authorization_rows) != 1 or len(nonce_rows) != 1:
        raise RegistryTransactionError(
            "AUTHORIZATION_OR_NONCE_LEDGER_CONFLICT",
            authorization_id,
        )
    if authorization_rows[0] != nonce_rows[0]:
        raise RegistryTransactionError(
            "AUTHORIZATION_OR_NONCE_REPLAY_CONFLICT",
            authorization_id,
        )
    return authorization_rows[0]


def _record_matches_retry(
    record: RegistryHistoryRecord,
    *,
    transaction_id: str,
    request: RegistryTransactionRequest,
    authorization: dict[str, Any],
    subject: RegistrySubject,
) -> bool:
    return all(
        (
            record.transaction_id == transaction_id,
            record.run_id == request.run_id,
            record.git_commit == request.git_commit,
            record.authorization_id == authorization["authorization_id"],
            record.authorization_seal_sha256 == authorization["seal_sha256"],
            record.transaction_nonce == request.transaction_nonce,
            record.expected_pre_state_sha256
            == request.expected_current_state_sha256,
            record.new_binding == subject,
        )
    )


def create_registry_transaction(
    *,
    p18_evidence_dir: Path,
    registry_path: Path,
    output_dir: Path,
    request: RegistryTransactionRequest,
    signature_verifier: SignatureVerifier | None = None,
) -> RegistryTransactionResult:
    source = p18_evidence_dir.resolve()
    output = _assert_output_available(output_dir, source)
    source_before = tree_sha256(source)
    p18 = read_p18_authorization(
        source,
        signature_verifier=signature_verifier,
    )
    authorization = dict(p18["authorization"])
    subject = RegistrySubject.model_validate(authorization["subject"])
    raw_registry = validate_registry_path(
        registry_path.absolute(),
        must_exist=True,
    )
    registry = validate_registry_target_matches_path(
        subject.registry_target,
        raw_registry,
    )
    transaction_id = transaction_identity(
        authorization=authorization,
        request=request,
    )

    with registry_lock(registry):
        pre_state = load_registry_state(registry)
        if pre_state.backend != BACKEND:
            raise RegistryTransactionError("REGISTRY_BACKEND_MISMATCH", pre_state.backend)
        if pre_state.registry_target != subject.registry_target:
            raise RegistryTransactionError(
                "REGISTRY_TARGET_MISMATCH",
                pre_state.registry_target,
            )
        existing = _matching_history_record(
            pre_state,
            authorization_id=str(authorization["authorization_id"]),
            transaction_nonce=request.transaction_nonce,
        )
        if existing is not None:
            if not _record_matches_retry(
                existing,
                transaction_id=transaction_id,
                request=request,
                authorization=authorization,
                subject=subject,
            ):
                raise RegistryTransactionError(
                    "AUTHORIZATION_OR_NONCE_REPLAY_CHANGED",
                    existing.transaction_id,
                )
            decision = "IDEMPOTENT_ALREADY_COMMITTED"
            registry_write_executed = False
            post_state = pre_state
            committed_record = existing
        else:
            if authorization_is_expired(authorization, request.executed_at_utc):
                raise RegistryTransactionError(
                    "AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID",
                    request.executed_at_utc,
                )
            if pre_state.state_sha256 != request.expected_current_state_sha256:
                raise RegistryTransactionError(
                    "REGISTRY_COMPARE_AND_SWAP_STALE",
                    (
                        f"expected={request.expected_current_state_sha256} "
                        f"actual={pre_state.state_sha256}"
                    ),
                )
            committed_record = make_history_record(
                transaction_id=transaction_id,
                run_id=request.run_id,
                git_commit=request.git_commit,
                authorization_id=str(authorization["authorization_id"]),
                authorization_seal_sha256=str(authorization["seal_sha256"]),
                transaction_nonce=request.transaction_nonce,
                committed_at_utc=request.executed_at_utc,
                expected_pre_state_sha256=pre_state.state_sha256,
                pre_generation=pre_state.generation,
                previous_binding=pre_state.current_binding,
                new_binding=subject,
            )
            post_state = make_registry_state(
                registry_target=pre_state.registry_target,
                generation=pre_state.generation + 1,
                current_binding=subject,
                consumed_authorization_ids=(
                    *pre_state.consumed_authorization_ids,
                    str(authorization["authorization_id"]),
                ),
                consumed_transaction_nonces=(
                    *pre_state.consumed_transaction_nonces,
                    request.transaction_nonce,
                ),
                history=(*pre_state.history, committed_record),
            )
            atomic_write_registry_state(registry, post_state)
            decision = "REGISTRY_TRANSACTION_COMMITTED"
            registry_write_executed = True

    observed_post_state = load_registry_state(registry)
    if observed_post_state != post_state:
        raise RegistryTransactionError("REGISTRY_POST_LOCK_STATE_MISMATCH", str(registry))
    if tree_sha256(source) != source_before:
        raise RegistryTransactionError("P18_SOURCE_MUTATED", str(source))

    invocation_id = canonical_sha256(
        {
            "transaction_id": transaction_id,
            "decision": decision,
            "pre_state_sha256": pre_state.state_sha256,
            "post_state_sha256": post_state.state_sha256,
            "run_id": request.run_id,
        }
    )
    payloads: dict[str, dict[str, Any]] = {
        "REQUEST_METADATA.json": {
            "schema_version": "autogluon-p19-request-metadata-v1",
            "phase": "AUTOGLUON_P19_REGISTRY_CAS",
            "run_id": request.run_id,
            "git_commit": request.git_commit,
            "executed_at_utc": request.executed_at_utc,
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
            "request": request.model_dump(mode="json"),
            "invocation_id": invocation_id,
        },
        "P18_LINEAGE.json": {
            "p18_tree_sha256": p18["source_tree_sha256"],
            "p18_authorization_file_sha256": p18["authorization_file_sha256"],
            "p18_requirements_file_sha256": p18["requirements_file_sha256"],
            "authorization": authorization,
            "transaction_requirements": p18["requirements"],
            "signature_verification_reperformed": True,
        },
        "TRANSACTION_PLAN.json": {
            "schema_version": "autogluon-p19-transaction-plan-v1",
            "backend": BACKEND,
            "transaction_id": transaction_id,
            "registry_target": subject.registry_target,
            "registry_path": str(registry),
            "expected_pre_state_sha256": request.expected_current_state_sha256,
            "authorization_id": authorization["authorization_id"],
            "authorization_seal_sha256": authorization["seal_sha256"],
            "transaction_nonce": request.transaction_nonce,
            "subject": subject.model_dump(mode="json"),
            "compare_and_swap": True,
            "one_time_consumption": True,
            "external_registry_adapter_enabled": False,
            "automatic_deployment": False,
            "automatic_retraining": False,
        },
        "PRE_REGISTRY_STATE.json": pre_state.model_dump(mode="json"),
        "TRANSACTION_RECEIPT.json": {
            "schema_version": "autogluon-p19-transaction-receipt-v1",
            "status": "PASS",
            "decision": decision,
            "transaction_id": transaction_id,
            "invocation_id": invocation_id,
            "registry_write_executed": registry_write_executed,
            "original_commit_record": committed_record.model_dump(mode="json"),
            "invocation_pre_state_sha256": pre_state.state_sha256,
            "post_state_sha256": post_state.state_sha256,
            "generation_before_invocation": pre_state.generation,
            "generation_after_invocation": post_state.generation,
        },
        "POST_REGISTRY_STATE.json": post_state.model_dump(mode="json"),
        "AUTHORIZATION_CONSUMPTION.json": {
            "schema_version": "autogluon-p19-authorization-consumption-v1",
            "authorization_id": authorization["authorization_id"],
            "authorization_seal_sha256": authorization["seal_sha256"],
            "transaction_nonce": request.transaction_nonce,
            "transaction_id": transaction_id,
            "consumed": True,
            "newly_consumed_by_this_invocation": registry_write_executed,
            "ledger_generation": post_state.generation,
        },
        "ROLLBACK_PLAN.json": {
            "schema_version": "autogluon-p19-rollback-plan-v1",
            "rollback_executed": False,
            "automatic_rollback": False,
            "previous_binding": (
                committed_record.previous_binding.model_dump(mode="json")
                if committed_record.previous_binding
                else None
            ),
            "registered_binding": subject.model_dump(mode="json"),
            "current_post_state_sha256": post_state.state_sha256,
            "requirements": [
                "fresh reviewed eligibility evidence",
                "fresh two-person authorization",
                "fresh transaction nonce",
                "compare-and-swap against current state",
            ],
        },
        "response.json": {
            "schema_version": P19_SCHEMA,
            "status": "PASS",
            "decision": decision,
            "transaction_id": transaction_id,
            "registry_backend": BACKEND,
            "registry_write_executed": registry_write_executed,
            "external_registry_write_executed": False,
            "model_registered": True,
            "promotion_status": "REGISTERED_NOT_DEPLOYED",
            "deployment_status": "NOT_DEPLOYED",
            "automatic_deployment": False,
            "automatic_retraining": False,
            "rollback_executed": False,
            "post_state_sha256": post_state.state_sha256,
        },
    }
    root = write_transaction_evidence(output, payloads)
    verified = verify_registry_transaction(root)
    return RegistryTransactionResult(
        output_dir=str(root),
        decision=verified["decision"],
        transaction_id=verified["transaction_id"],
        registry_write_executed=verified["registry_write_executed"],
        post_state_sha256=verified["post_state_sha256"],
    )


def _verify_history_membership(
    state: RegistryState,
    record: RegistryHistoryRecord,
) -> None:
    matches = [row for row in state.history if row.transaction_id == record.transaction_id]
    if matches != [record]:
        raise RegistryTransactionError(
            "TRANSACTION_HISTORY_MEMBERSHIP_MISMATCH",
            record.transaction_id,
        )


def verify_registry_transaction(root: Path) -> dict[str, Any]:
    evidence = root.resolve()
    verify_transaction_evidence_files(evidence)
    metadata = load_json(evidence / "REQUEST_METADATA.json")
    request = RegistryTransactionRequest.model_validate(metadata["request"])
    lineage = load_json(evidence / "P18_LINEAGE.json")
    authorization = dict(lineage["authorization"])
    verify_registry_authorization(authorization)
    requirements = dict(lineage["transaction_requirements"])
    if requirements.get("authorization_id") != authorization["authorization_id"]:
        raise RegistryTransactionError("P18_LINEAGE_AUTHORIZATION_MISMATCH", str(evidence))
    if requirements.get("authorization_seal_sha256") != authorization["seal_sha256"]:
        raise RegistryTransactionError("P18_LINEAGE_SEAL_MISMATCH", str(evidence))
    if requirements.get("expected_subject") != authorization["subject"]:
        raise RegistryTransactionError("P18_LINEAGE_SUBJECT_MISMATCH", str(evidence))
    required_true = (
        "expected_current_registry_state_sha256_required",
        "compare_and_swap_required",
        "append_only_consumption_ledger_required",
        "authorization_must_be_unexpired",
        "authorization_must_be_unconsumed",
    )
    if any(requirements.get(key) is not True for key in required_true):
        raise RegistryTransactionError(
            "P18_LINEAGE_REQUIREMENT_INVALID",
            str(evidence),
        )
    if requirements.get("registry_write_executed") is not False:
        raise RegistryTransactionError(
            "P18_LINEAGE_EXECUTION_STATE_INVALID",
            str(evidence),
        )

    plan = load_json(evidence / "TRANSACTION_PLAN.json")
    subject = RegistrySubject.model_validate(authorization["subject"])
    expected_transaction_id = transaction_identity(
        authorization=authorization,
        request=request,
    )
    if plan.get("transaction_id") != expected_transaction_id:
        raise RegistryTransactionError("TRANSACTION_ID_MISMATCH", str(evidence))
    if plan.get("subject") != subject.model_dump(mode="json"):
        raise RegistryTransactionError("TRANSACTION_PLAN_SUBJECT_MISMATCH", str(evidence))
    if plan.get("registry_target") != subject.registry_target:
        raise RegistryTransactionError("TRANSACTION_PLAN_TARGET_MISMATCH", str(evidence))
    if plan.get("expected_pre_state_sha256") != request.expected_current_state_sha256:
        raise RegistryTransactionError("TRANSACTION_PLAN_PRE_STATE_MISMATCH", str(evidence))

    pre_state = RegistryState.model_validate(
        load_json(evidence / "PRE_REGISTRY_STATE.json")
    )
    post_state = RegistryState.model_validate(
        load_json(evidence / "POST_REGISTRY_STATE.json")
    )
    receipt = load_json(evidence / "TRANSACTION_RECEIPT.json")
    record = RegistryHistoryRecord.model_validate(receipt["original_commit_record"])
    _verify_history_membership(post_state, record)
    consumption = load_json(evidence / "AUTHORIZATION_CONSUMPTION.json")
    rollback = load_json(evidence / "ROLLBACK_PLAN.json")
    response = load_json(evidence / "response.json")
    decision = str(receipt.get("decision"))

    if record.transaction_id != expected_transaction_id:
        raise RegistryTransactionError("RECEIPT_TRANSACTION_ID_MISMATCH", str(evidence))
    if record.run_id != request.run_id or record.git_commit != request.git_commit:
        raise RegistryTransactionError("RECEIPT_REQUEST_IDENTITY_MISMATCH", str(evidence))
    if record.authorization_id != authorization["authorization_id"]:
        raise RegistryTransactionError("RECEIPT_AUTHORIZATION_MISMATCH", str(evidence))
    if record.authorization_seal_sha256 != authorization["seal_sha256"]:
        raise RegistryTransactionError("RECEIPT_AUTHORIZATION_SEAL_MISMATCH", str(evidence))
    if record.transaction_nonce != request.transaction_nonce:
        raise RegistryTransactionError("RECEIPT_NONCE_MISMATCH", str(evidence))
    if record.new_binding != subject:
        raise RegistryTransactionError("RECEIPT_SUBJECT_MISMATCH", str(evidence))

    if decision == "REGISTRY_TRANSACTION_COMMITTED":
        if receipt.get("registry_write_executed") is not True:
            raise RegistryTransactionError("COMMIT_WRITE_FLAG_INVALID", str(evidence))
        if pre_state.state_sha256 != request.expected_current_state_sha256:
            raise RegistryTransactionError("COMMIT_PRE_STATE_MISMATCH", str(evidence))
        if post_state.generation != pre_state.generation + 1:
            raise RegistryTransactionError("COMMIT_GENERATION_MISMATCH", str(evidence))
        if post_state.history != (*pre_state.history, record):
            raise RegistryTransactionError("COMMIT_HISTORY_NOT_APPEND_ONLY", str(evidence))
        if post_state.consumed_authorization_ids != (
            *pre_state.consumed_authorization_ids,
            str(authorization["authorization_id"]),
        ):
            raise RegistryTransactionError("COMMIT_AUTH_LEDGER_NOT_APPEND_ONLY", str(evidence))
        if post_state.consumed_transaction_nonces != (
            *pre_state.consumed_transaction_nonces,
            request.transaction_nonce,
        ):
            raise RegistryTransactionError("COMMIT_NONCE_LEDGER_NOT_APPEND_ONLY", str(evidence))
        if consumption.get("newly_consumed_by_this_invocation") is not True:
            raise RegistryTransactionError("COMMIT_CONSUMPTION_FLAG_INVALID", str(evidence))
    elif decision == "IDEMPOTENT_ALREADY_COMMITTED":
        if receipt.get("registry_write_executed") is not False:
            raise RegistryTransactionError("IDEMPOTENT_WRITE_FLAG_INVALID", str(evidence))
        if pre_state != post_state:
            raise RegistryTransactionError("IDEMPOTENT_STATE_CHANGED", str(evidence))
        if consumption.get("newly_consumed_by_this_invocation") is not False:
            raise RegistryTransactionError("IDEMPOTENT_CONSUMPTION_FLAG_INVALID", str(evidence))
    else:
        raise RegistryTransactionError("TRANSACTION_DECISION_INVALID", decision)

    if post_state.current_binding != subject:
        raise RegistryTransactionError("POST_STATE_BINDING_MISMATCH", str(evidence))
    if consumption != {
        "schema_version": "autogluon-p19-authorization-consumption-v1",
        "authorization_id": authorization["authorization_id"],
        "authorization_seal_sha256": authorization["seal_sha256"],
        "transaction_nonce": request.transaction_nonce,
        "transaction_id": expected_transaction_id,
        "consumed": True,
        "newly_consumed_by_this_invocation": receipt["registry_write_executed"],
        "ledger_generation": post_state.generation,
    }:
        raise RegistryTransactionError("AUTHORIZATION_CONSUMPTION_MISMATCH", str(evidence))
    if rollback.get("rollback_executed") is not False:
        raise RegistryTransactionError("ROLLBACK_EXECUTION_FORBIDDEN", str(evidence))
    if rollback.get("current_post_state_sha256") != post_state.state_sha256:
        raise RegistryTransactionError("ROLLBACK_STATE_MISMATCH", str(evidence))

    expected_invocation_id = canonical_sha256(
        {
            "transaction_id": expected_transaction_id,
            "decision": decision,
            "pre_state_sha256": pre_state.state_sha256,
            "post_state_sha256": post_state.state_sha256,
            "run_id": request.run_id,
        }
    )
    if metadata.get("invocation_id") != expected_invocation_id:
        raise RegistryTransactionError("INVOCATION_ID_MISMATCH", str(evidence))
    if receipt.get("invocation_id") != expected_invocation_id:
        raise RegistryTransactionError("RECEIPT_INVOCATION_ID_MISMATCH", str(evidence))

    expected_response = {
        "schema_version": P19_SCHEMA,
        "status": "PASS",
        "decision": decision,
        "transaction_id": expected_transaction_id,
        "registry_backend": BACKEND,
        "registry_write_executed": receipt["registry_write_executed"],
        "external_registry_write_executed": False,
        "model_registered": True,
        "promotion_status": "REGISTERED_NOT_DEPLOYED",
        "deployment_status": "NOT_DEPLOYED",
        "automatic_deployment": False,
        "automatic_retraining": False,
        "rollback_executed": False,
        "post_state_sha256": post_state.state_sha256,
    }
    if response != expected_response:
        raise RegistryTransactionError("P19_RESPONSE_MISMATCH", str(evidence))
    return {
        "status": "PASS",
        "decision": decision,
        "transaction_id": expected_transaction_id,
        "registry_write_executed": bool(receipt["registry_write_executed"]),
        "post_state_sha256": post_state.state_sha256,
        "tree_sha256": transaction_output_tree_sha256(evidence),
        "promotion_status": "REGISTERED_NOT_DEPLOYED",
    }


__all__ = [
    "create_registry_transaction",
    "verify_registry_transaction",
]
