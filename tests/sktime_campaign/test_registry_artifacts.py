from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.registry_artifacts import (
    P8VerificationError,
    persist_p8,
    verify_p8,
)
from loto.sktime_campaign.registry_transaction import bootstrap_registry
from tests.sktime_campaign.test_registry_transaction import request, subject


def run_case(tmp_path: Path):
    state_path = tmp_path / "registry.json"
    state = bootstrap_registry(state_path, subject(state_path).registry_target)
    output = tmp_path / "evidence"
    transaction = request(state_path, state.state_sha256).model_copy(
        update={"output_dir": str(output)}
    )
    persist_p8(
        transaction,
        committed_at_utc="2026-08-05T10:20:00Z",
    )
    return output, transaction


def test_persist_and_verify(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    result = verify_p8(output, transaction)
    assert result["status"] == "PASS"
    assert result["deployment_status"] == "NOT_DEPLOYED"


def test_artifacts_complete(tmp_path: Path) -> None:
    output, _ = run_case(tmp_path)
    assert {path.name for path in output.iterdir()} == {
        "REQUEST_METADATA.json",
        "P7_LINEAGE.json",
        "TRANSACTION_PLAN.json",
        "PRE_REGISTRY_STATE.json",
        "TRANSACTION_RECEIPT.json",
        "POST_REGISTRY_STATE.json",
        "AUTHORIZATION_CONSUMPTION.json",
        "ROLLBACK_PLAN.json",
        "response.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }


def mutate(path: Path, key: str, value) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_receipt_tamper_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    mutate(output / "TRANSACTION_RECEIPT.json", "transaction_id", "0" * 64)
    with pytest.raises(P8VerificationError):
        verify_p8(output, transaction)


def test_post_state_tamper_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    mutate(output / "POST_REGISTRY_STATE.json", "generation", 9)
    with pytest.raises((P8VerificationError, ValueError)):
        verify_p8(output, transaction)


def test_response_deployment_tamper_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    mutate(output / "response.json", "automatic_deployment", True)
    with pytest.raises(P8VerificationError):
        verify_p8(output, transaction)


def test_rollback_tamper_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    mutate(output / "ROLLBACK_PLAN.json", "automatic_rollback", True)
    with pytest.raises(P8VerificationError):
        verify_p8(output, transaction)


def test_manifest_tamper_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    mutate(output / "ARTIFACT_MANIFEST.json", "scope", "bad")
    with pytest.raises(P8VerificationError):
        verify_p8(output, transaction)


def test_sha_coverage_rejected(tmp_path: Path) -> None:
    output, transaction = run_case(tmp_path)
    manifest = output / "SHA256SUMS"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    manifest.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(P8VerificationError):
        verify_p8(output, transaction)
