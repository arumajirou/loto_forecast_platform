from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from loto.autogluon_campaign.approval_authorization_io import (
    tree_sha256,
    write_evidence,
)
from loto.autogluon_campaign.registry_transaction import (
    create_registry_transaction,
    verify_registry_transaction,
)
from loto.autogluon_campaign.registry_transaction_contract import (
    RegistryTransactionError,
)
from loto.autogluon_campaign.registry_transaction_io import load_registry_state
from tests.autogluon_campaign.p18_test_support import always_verify
from tests.autogluon_campaign.p19_test_support import (
    make_p18_bundle,
    make_registry,
    make_request,
)


def committed_transaction(tmp_path: Path):
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    request = make_request(initial_sha)
    output = tmp_path / "p19-commit"
    result = create_registry_transaction(
        p18_evidence_dir=p18,
        registry_path=registry,
        output_dir=output,
        request=request,
        signature_verifier=always_verify,
    )
    return registry, p18, request, output, result


def test_successful_transaction_commits_once(tmp_path: Path) -> None:
    registry, _, _, output, result = committed_transaction(tmp_path)
    state = load_registry_state(registry)
    assert result.decision == "REGISTRY_TRANSACTION_COMMITTED"
    assert result.registry_write_executed is True
    assert state.generation == 1
    assert len(state.history) == 1
    assert state.current_binding is not None
    verified = verify_registry_transaction(output)
    assert verified["status"] == "PASS"
    assert verified["promotion_status"] == "REGISTERED_NOT_DEPLOYED"


def test_success_does_not_deploy_or_retrain(tmp_path: Path) -> None:
    _, _, _, output, _ = committed_transaction(tmp_path)
    response = json.loads((output / "response.json").read_text(encoding="utf-8"))
    assert response["deployment_status"] == "NOT_DEPLOYED"
    assert response["automatic_deployment"] is False
    assert response["automatic_retraining"] is False
    assert response["external_registry_write_executed"] is False
    assert response["rollback_executed"] is False


def test_exact_retry_is_idempotent_without_registry_mutation(tmp_path: Path) -> None:
    registry, p18, request, _, first = committed_transaction(tmp_path)
    before = registry.read_bytes()
    retry = create_registry_transaction(
        p18_evidence_dir=p18,
        registry_path=registry,
        output_dir=tmp_path / "p19-retry",
        request=request,
        signature_verifier=always_verify,
    )
    assert retry.decision == "IDEMPOTENT_ALREADY_COMMITTED"
    assert retry.registry_write_executed is False
    assert retry.transaction_id == first.transaction_id
    assert registry.read_bytes() == before
    verify_registry_transaction(tmp_path / "p19-retry")


def test_stale_expected_state_fails_without_mutation(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    before = registry.read_bytes()
    request = make_request("f" * 64)
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / "blocked",
            request=request,
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "REGISTRY_COMPARE_AND_SWAP_STALE"
    assert registry.read_bytes() == before
    assert load_registry_state(registry).state_sha256 == initial_sha


def test_expired_authorization_fails_without_mutation(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    before = registry.read_bytes()
    request = make_request(initial_sha, executed_at="2026-08-05T11:00:01Z")
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / "expired",
            request=request,
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID"
    assert registry.read_bytes() == before


def test_changed_retry_with_same_authorization_is_rejected(tmp_path: Path) -> None:
    registry, p18, request, _, _ = committed_transaction(tmp_path)
    changed = make_request(
        request.expected_current_state_sha256,
        transaction_nonce="c" * 64,
    )
    before = registry.read_bytes()
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / "changed-retry",
            request=changed,
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "AUTHORIZATION_OR_NONCE_LEDGER_CONFLICT"
    assert registry.read_bytes() == before


def test_reused_transaction_nonce_with_new_authorization_is_rejected(
    tmp_path: Path,
) -> None:
    registry, _, request, _, _ = committed_transaction(tmp_path)
    current = load_registry_state(registry)
    second_p18 = make_p18_bundle(
        tmp_path,
        registry,
        name="p18-second",
        authorization_nonce="d" * 64,
        revision="abcdef0123456789",
    )
    second_request = make_request(
        current.state_sha256,
        run_id="p19-second",
        transaction_nonce=request.transaction_nonce,
    )
    before = registry.read_bytes()
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=second_p18,
            registry_path=registry,
            output_dir=tmp_path / "nonce-reuse",
            request=second_request,
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "AUTHORIZATION_OR_NONCE_LEDGER_CONFLICT"
    assert registry.read_bytes() == before


def test_registry_target_path_mismatch_is_rejected(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    other = tmp_path / "registry" / "other.json"
    other.write_bytes(registry.read_bytes())
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=other,
            output_dir=tmp_path / "target-mismatch",
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "REGISTRY_TARGET_PATH_MISMATCH"


def test_symlink_registry_path_is_rejected(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    link = tmp_path / "registry-link.json"
    link.symlink_to(registry)
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=link,
            output_dir=tmp_path / "symlink-output",
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert exc_info.value.code in {
        "REGISTRY_TARGET_PATH_MISMATCH",
        "SYMLINK_FORBIDDEN",
    }


def test_nonempty_output_is_rejected_before_mutation(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    output = tmp_path / "nonempty"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    before = registry.read_bytes()
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=output,
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "OUTPUT_NOT_EMPTY"
    assert registry.read_bytes() == before


def test_output_inside_p18_source_is_rejected(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    before = tree_sha256(p18)
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=p18 / "nested-output",
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "OUTPUT_INSIDE_P18_SOURCE"
    assert tree_sha256(p18) == before


def test_p18_source_remains_byte_immutable(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    before = tree_sha256(p18)
    create_registry_transaction(
        p18_evidence_dir=p18,
        registry_path=registry,
        output_dir=tmp_path / "output",
        request=make_request(initial_sha),
        signature_verifier=always_verify,
    )
    assert tree_sha256(p18) == before


def test_output_file_tamper_is_detected(tmp_path: Path) -> None:
    _, _, _, output, _ = committed_transaction(tmp_path)
    path = output / "response.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("NOT_DEPLOYED", "DEPLOYED"),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        verify_registry_transaction(output)


def test_semantic_tamper_is_detected_after_rehash(tmp_path: Path) -> None:
    _, _, _, output, _ = committed_transaction(tmp_path)
    path = output / "response.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["automatic_deployment"] = True
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload_names = [
        item.name
        for item in output.iterdir()
        if item.is_file() and item.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(output, payload_names)
    with pytest.raises(RegistryTransactionError) as exc_info:
        verify_registry_transaction(output)
    assert exc_info.value.code == "P19_RESPONSE_MISMATCH"


def test_registry_history_record_tamper_is_detected(tmp_path: Path) -> None:
    registry, _, _, _, _ = committed_transaction(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["history"][0]["run_id"] = "changed"
    registry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RegistryTransactionError) as exc_info:
        load_registry_state(registry)
    assert exc_info.value.code == "REGISTRY_STATE_INVALID"


def test_concurrent_exact_requests_commit_once(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    request = make_request(initial_sha)

    def run(index: int):
        return create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / f"concurrent-{index}",
            request=request,
            signature_verifier=always_verify,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    decisions = sorted(result.decision for result in results)
    assert decisions == [
        "IDEMPOTENT_ALREADY_COMMITTED",
        "REGISTRY_TRANSACTION_COMMITTED",
    ]
    assert load_registry_state(registry).generation == 1


def test_exact_retry_after_authorization_expiry_remains_read_only(tmp_path: Path) -> None:
    registry, p18, request, _, _ = committed_transaction(tmp_path)
    before = registry.read_bytes()
    expired_retry = make_request(
        request.expected_current_state_sha256,
        run_id=request.run_id,
        transaction_nonce=request.transaction_nonce,
        executed_at="2026-08-05T12:00:00Z",
    )
    result = create_registry_transaction(
        p18_evidence_dir=p18,
        registry_path=registry,
        output_dir=tmp_path / "expired-idempotent-retry",
        request=expired_retry,
        signature_verifier=always_verify,
    )
    assert result.decision == "IDEMPOTENT_ALREADY_COMMITTED"
    assert result.registry_write_executed is False
    assert registry.read_bytes() == before


def test_p18_semantic_tamper_blocks_before_registry_mutation(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    response_path = p18 / "response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["registry_write_authorized"] = False
    response_path.write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    names = [
        path.name
        for path in p18.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(p18, names)
    before = registry.read_bytes()
    with pytest.raises(Exception):
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / "blocked-p18",
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert registry.read_bytes() == before


def test_symlink_parent_component_is_rejected(tmp_path: Path) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    linked_parent = tmp_path / "linked-registry-parent"
    linked_parent.symlink_to(registry.parent, target_is_directory=True)
    linked_path = linked_parent / registry.name
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=linked_path,
            output_dir=tmp_path / "linked-parent-output",
            request=make_request(initial_sha),
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "SYMLINK_FORBIDDEN"


def test_p18_lineage_semantic_tamper_is_detected_after_rehash(tmp_path: Path) -> None:
    _, _, _, output, _ = committed_transaction(tmp_path)
    lineage_path = output / "P18_LINEAGE.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["transaction_requirements"]["compare_and_swap_required"] = False
    lineage_path.write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload_names = [
        path.name
        for path in output.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(output, payload_names)
    with pytest.raises(RegistryTransactionError):
        verify_registry_transaction(output)


def test_retry_with_changed_git_commit_is_rejected(tmp_path: Path) -> None:
    registry, p18, request, _, _ = committed_transaction(tmp_path)
    changed = request.model_copy(update={"git_commit": "a" * 40})
    before = registry.read_bytes()
    with pytest.raises(RegistryTransactionError) as exc_info:
        create_registry_transaction(
            p18_evidence_dir=p18,
            registry_path=registry,
            output_dir=tmp_path / "changed-git-retry",
            request=changed,
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "AUTHORIZATION_OR_NONCE_REPLAY_CHANGED"
    assert registry.read_bytes() == before


def test_rehashed_history_chain_tamper_is_rejected(tmp_path: Path) -> None:
    from loto.autogluon_campaign.approval_authorization_contract import canonical_sha256

    registry, _, _, _, _ = committed_transaction(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    record = payload["history"][0]
    record["expected_pre_state_sha256"] = "f" * 64
    record_core = dict(record)
    record_core.pop("record_sha256")
    record["record_sha256"] = canonical_sha256(record_core)
    state_core = dict(payload)
    state_core.pop("state_sha256")
    payload["state_sha256"] = canonical_sha256(state_core)
    registry.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryTransactionError) as exc_info:
        load_registry_state(registry)
    assert exc_info.value.code == "REGISTRY_STATE_INVALID"
