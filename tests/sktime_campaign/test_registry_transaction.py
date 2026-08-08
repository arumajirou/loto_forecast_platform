from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from loto.sktime_campaign.approval_authorization import (
    RegistrySubject,
    RegistryTransactionRequest,
    canonical_sha256,
)
from loto.sktime_campaign.registry_transaction import (
    P8RegistryTransactionRequest,
    bootstrap_registry,
    commit_registry_transaction,
)

H = "a" * 64


def subject(path: Path, *, model: str = "model-1") -> RegistrySubject:
    return RegistrySubject(
        registry_target=f"file+json://{path}",
        model_id=model,
        model_revision="abcdef1",
        shadow_candidate_id="naive_last",
        model_artifact_sha256="1" * 64,
        data_snapshot_sha256="2" * 64,
        runtime_environment_sha256="3" * 64,
        code_sha256="4" * 64,
    )


def authorization(value: RegistrySubject) -> dict:
    payload = {
        "schema_version": "1.0",
        "authorization_scope": "ONE_EXACT_REGISTRY_TRANSACTION",
        "authorization_id": "5" * 64,
        "issued_at_utc": "2026-08-05T10:00:00Z",
        "expires_at_utc": "2026-08-05T11:00:00Z",
        "approval_intent_sha256": "6" * 64,
        "p6_bundle_sha256": "7" * 64,
        "p6_decision_sha256": "8" * 64,
        "subject": value.model_dump(mode="json"),
        "approval_evidence": [],
        "authorization_nonce": "9" * 64,
        "one_time_use": True,
        "consumed": False,
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
    return {**payload, "seal_sha256": canonical_sha256(payload)}


def request(
    path: Path,
    state_hash: str,
    *,
    tx_nonce: str = "b" * 64,
    model: str = "model-1",
) -> P8RegistryTransactionRequest:
    value = subject(path, model=model)
    approval = authorization(value)
    transaction = RegistryTransactionRequest(
        authorization_id=approval["authorization_id"],
        authorization_seal_sha256=approval["seal_sha256"],
        transaction_nonce=tx_nonce,
        requested_at_utc="2026-08-05T10:10:00Z",
        expected_registry_state_sha256=state_hash,
        subject=value,
    )
    return P8RegistryTransactionRequest(
        output_dir="/tmp/out",
        run_id="run-1",
        git_commit="abcdef1",
        code_sha256=H,
        config_sha256=H,
        p7_bundle_sha256=H,
        registry_state_path=str(path),
        authorization=approval,
        transaction=transaction,
    )


def test_bootstrap_and_commit(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    result = commit_registry_transaction(
        request(path, state.state_sha256),
        committed_at_utc="2026-08-05T10:20:00Z",
    )
    assert result["decision"] == "REGISTRY_TRANSACTION_COMMITTED"
    assert result["registry_write_executed"] is True
    assert result["post_state"]["generation"] == 1
    binding = result["post_state"]["current_binding"]
    assert binding["subject"]["model_id"] == "model-1"
    assert result["deployment_status"] == "NOT_DEPLOYED"


def test_stale_cas_rejected_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    bootstrap_registry(path, subject(path).registry_target)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="pre-state mismatch"):
        commit_registry_transaction(
            request(path, "0" * 64),
            committed_at_utc="2026-08-05T10:20:00Z",
        )
    assert path.read_bytes() == before


def test_expired_authorization_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    with pytest.raises(ValueError, match="outside authorization window"):
        commit_registry_transaction(
            request(path, state.state_sha256),
            committed_at_utc="2026-08-05T11:00:01Z",
        )


def test_exact_replay_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    transaction = request(path, state.state_sha256)
    first = commit_registry_transaction(
        transaction,
        committed_at_utc="2026-08-05T10:20:00Z",
    )
    before = path.read_bytes()
    second = commit_registry_transaction(
        transaction,
        committed_at_utc="2026-08-05T10:30:00Z",
    )
    assert second["decision"] == "IDEMPOTENT_ALREADY_COMMITTED"
    assert second["registry_write_executed"] is False
    assert second["transaction_id"] == first["transaction_id"]
    assert path.read_bytes() == before


def test_changed_nonce_after_consumption_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    commit_registry_transaction(
        request(path, state.state_sha256),
        committed_at_utc="2026-08-05T10:20:00Z",
    )
    latest = json.loads(path.read_text(encoding="utf-8"))
    changed = request(path, latest["state_sha256"], tx_nonce="c" * 64)
    with pytest.raises(ValueError, match="changed transaction nonce"):
        commit_registry_transaction(
            changed,
            committed_at_utc="2026-08-05T10:30:00Z",
        )


def test_subject_mismatch_rejected_by_request(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    data = request(path, state.state_sha256).model_dump(mode="json")
    data["transaction"]["subject"]["model_id"] = "changed"
    with pytest.raises(ValueError, match="subject differs"):
        P8RegistryTransactionRequest.model_validate(data)


def test_registry_target_path_mismatch_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    data = request(path, state.state_sha256).model_dump(mode="json")
    data["registry_state_path"] = str(tmp_path / "other.json")
    with pytest.raises(ValueError, match="path differs"):
        P8RegistryTransactionRequest.model_validate(data)


def test_symlink_registry_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    state = bootstrap_registry(real, subject(real).registry_target)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    transaction = request(real, state.state_sha256).model_copy(
        update={"registry_state_path": str(link)}
    )
    with pytest.raises(ValueError, match="symlink"):
        commit_registry_transaction(
            transaction,
            committed_at_utc="2026-08-05T10:20:00Z",
        )


def test_tampered_state_rejected(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["generation"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        commit_registry_transaction(
            request(path, state.state_sha256),
            committed_at_utc="2026-08-05T10:20:00Z",
        )


def test_bootstrap_refuses_existing(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        bootstrap_registry(path, subject(path).registry_target)


def _second_authorization(
    base: P8RegistryTransactionRequest,
) -> P8RegistryTransactionRequest:
    data = base.model_dump(mode="json")
    data["authorization"]["authorization_id"] = "d" * 64
    payload = {key: value for key, value in data["authorization"].items() if key != "seal_sha256"}
    data["authorization"]["seal_sha256"] = canonical_sha256(payload)
    data["transaction"]["authorization_id"] = "d" * 64
    data["transaction"]["authorization_seal_sha256"] = data["authorization"]["seal_sha256"]
    return P8RegistryTransactionRequest.model_validate(data)


def test_concurrent_stale_transactions_only_one_commits(
    tmp_path: Path,
) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    first = request(path, state.state_sha256)
    second = _second_authorization(request(path, state.state_sha256, tx_nonce="c" * 64))

    def execute(item: P8RegistryTransactionRequest) -> str:
        try:
            result = commit_registry_transaction(
                item,
                committed_at_utc="2026-08-05T10:20:00Z",
            )
            return str(result["decision"])
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(execute, [first, second]))
    assert outcomes.count("REGISTRY_TRANSACTION_COMMITTED") == 1
    assert sum("pre-state mismatch" in item for item in outcomes) == 1


def test_previous_binding_retained_for_rollback(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    state = bootstrap_registry(path, subject(path).registry_target)
    commit_registry_transaction(
        request(path, state.state_sha256),
        committed_at_utc="2026-08-05T10:20:00Z",
    )
    latest = json.loads(path.read_text(encoding="utf-8"))
    second = request(
        path,
        latest["state_sha256"],
        tx_nonce="e" * 64,
        model="model-2",
    )
    second = _second_authorization(second)
    result = commit_registry_transaction(
        second,
        committed_at_utc="2026-08-05T10:30:00Z",
    )
    previous = result["history_record"]["previous_binding"]
    current = result["history_record"]["new_binding"]
    assert previous["subject"]["model_id"] == "model-1"
    assert current["subject"]["model_id"] == "model-2"
