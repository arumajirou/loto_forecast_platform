from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.autogluon_campaign.registry_transaction_contract import (
    RegistryPolicy,
    RegistryState,
    RegistryTransactionError,
    RegistryTransactionRequest,
    registry_target_to_path,
    validate_registry_target_matches_path,
)
from loto.autogluon_campaign.registry_transaction_io import (
    bootstrap_registry,
    load_registry_state,
)
from tests.autogluon_campaign.p19_test_support import (
    make_registry,
    registry_target,
)


def test_bootstrap_creates_verified_empty_state(tmp_path: Path) -> None:
    path, target, state_sha = make_registry(tmp_path)
    state = load_registry_state(path)
    assert state.registry_target == target
    assert state.generation == 0
    assert state.current_binding is None
    assert state.history == ()
    assert state.state_sha256 == state_sha
    assert state.deployment_status == "NOT_DEPLOYED"


def test_bootstrap_rejects_existing_registry(tmp_path: Path) -> None:
    path, target, _ = make_registry(tmp_path)
    with pytest.raises(RegistryTransactionError) as exc_info:
        bootstrap_registry(registry_path=path, registry_target=target)
    assert exc_info.value.code == "REGISTRY_STATE_ALREADY_EXISTS"


@pytest.mark.parametrize(
    "target",
    [
        "file:///tmp/registry.json",
        "https://example.invalid/registry.json",
        "file+json://host/tmp/registry.json",
        "file+json:///tmp/registry.json?version=1",
        "relative.json",
    ],
)
def test_registry_target_parser_is_fail_closed(target: str) -> None:
    with pytest.raises(RegistryTransactionError):
        registry_target_to_path(target)


def test_registry_target_path_mismatch_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    with pytest.raises(RegistryTransactionError) as exc_info:
        validate_registry_target_matches_path(registry_target(first), second)
    assert exc_info.value.code == "REGISTRY_TARGET_PATH_MISMATCH"


def test_registry_policy_forbids_external_adapter() -> None:
    with pytest.raises(ValidationError):
        RegistryPolicy(external_registry_adapter_enabled=True)


def test_registry_policy_forbids_automatic_deployment() -> None:
    with pytest.raises(ValidationError):
        RegistryPolicy(automatic_deployment=True)


def test_transaction_request_requires_sha_nonce() -> None:
    with pytest.raises(ValidationError):
        RegistryTransactionRequest(
            run_id="run",
            git_commit="4830d3d",
            expected_current_state_sha256="1" * 64,
            transaction_nonce="short",
            executed_at_utc="2026-08-05T10:40:00Z",
        )


def test_registry_state_self_hash_tamper_is_rejected(tmp_path: Path) -> None:
    path, _, _ = make_registry(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["generation"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RegistryTransactionError) as exc_info:
        load_registry_state(path)
    assert exc_info.value.code == "REGISTRY_STATE_INVALID"


def test_registry_state_rejects_duplicate_consumption_ledgers(tmp_path: Path) -> None:
    path, _, _ = make_registry(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["consumed_authorization_ids"] = ["a" * 64, "a" * 64]
    payload["consumed_transaction_nonces"] = ["b" * 64, "c" * 64]
    payload["generation"] = 2
    with pytest.raises(ValidationError):
        RegistryState.model_validate(payload)


def test_registry_target_rejects_parent_traversal() -> None:
    with pytest.raises(RegistryTransactionError) as exc_info:
        registry_target_to_path("file+json:///tmp/registry/../state.json")
    assert exc_info.value.code == "REGISTRY_TARGET_PATH_UNSAFE"
