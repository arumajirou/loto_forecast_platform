from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.autogluon_campaign import approval_authorization as authorization_module
from loto.autogluon_campaign.approval_authorization import (
    create_approval_authorization,
    verify_approval_authorization,
)
from loto.autogluon_campaign.approval_authorization_cli import main
from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
)
from loto.autogluon_campaign.approval_authorization_io import (
    load_json,
    write_evidence,
    write_json,
)
from tests.autogluon_campaign.p18_test_support import (
    always_verify,
    make_approvals,
    make_intent,
)


def make_run(tmp_path: Path) -> tuple[Path, Path, object, list]:
    p17, signers, intent = make_intent(tmp_path)
    approvals = make_approvals(intent)
    output = tmp_path / "p18"
    result = create_approval_authorization(
        p17_evidence_dir=p17,
        intent=intent,
        approvals=approvals,
        allowed_signers_file=signers,
        output_dir=output,
        issued_at_utc="2026-08-05T10:30:00Z",
        signature_verifier=always_verify,
    )
    return output, signers, result, approvals


def test_complete_authorization_artifact_verifies(tmp_path: Path) -> None:
    output, _, result, _ = make_run(tmp_path)
    verified = verify_approval_authorization(
        output,
        signature_verifier=always_verify,
    )
    assert result.status == "PASS"
    assert verified["status"] == "PASS"
    assert verified["registry_write_executed"] is False


def test_output_directory_must_be_empty(tmp_path: Path) -> None:
    p17, signers, intent = make_intent(tmp_path)
    output = tmp_path / "p18"
    output.mkdir()
    (output / "stale.json").write_text("{}")
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        create_approval_authorization(
            p17_evidence_dir=p17,
            intent=intent,
            approvals=make_approvals(intent),
            allowed_signers_file=signers,
            output_dir=output,
            issued_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "OUTPUT_NOT_EMPTY"


def test_allowed_signers_hash_change_is_rejected(tmp_path: Path) -> None:
    p17, signers, intent = make_intent(tmp_path)
    signers.write_text(signers.read_text() + "extra ssh-ed25519 key\n")
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        create_approval_authorization(
            p17_evidence_dir=p17,
            intent=intent,
            approvals=make_approvals(intent),
            allowed_signers_file=signers,
            output_dir=tmp_path / "p18",
            issued_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "ALLOWED_SIGNERS_HASH_MISMATCH"


def test_output_file_tampering_is_rejected(tmp_path: Path) -> None:
    output, _, _, _ = make_run(tmp_path)
    response = output / "response.json"
    response.write_text(response.read_text().replace("APPROVED_NOT_REGISTERED", "PROMOTED"))
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_authorization(output, signature_verifier=always_verify)
    assert exc_info.value.code == "SHA256_MISMATCH"


def test_semantic_tampering_after_rehash_is_rejected(tmp_path: Path) -> None:
    output, _, _, _ = make_run(tmp_path)
    response = load_json(output / "response.json")
    response["promotion_status"] = "PROMOTED"
    write_json(output / "response.json", response)
    payloads = [
        path.name
        for path in output.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(output, payloads)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_authorization(output, signature_verifier=always_verify)
    assert exc_info.value.code == "P18_RESPONSE_MISMATCH"


def test_signature_evidence_tampering_after_rehash_is_rejected(tmp_path: Path) -> None:
    output, _, _, _ = make_run(tmp_path)
    evidence = load_json(output / "SIGNATURE_VERIFICATION.json")
    evidence["approvals"][0]["approver_id"] = "attacker@example"
    write_json(output / "SIGNATURE_VERIFICATION.json", evidence)
    payloads = [
        path.name
        for path in output.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(output, payloads)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_authorization(output, signature_verifier=always_verify)
    assert exc_info.value.code == "SIGNATURE_EVIDENCE_MISMATCH"


def test_transaction_subject_tampering_after_rehash_is_rejected(tmp_path: Path) -> None:
    output, _, _, _ = make_run(tmp_path)
    transaction = load_json(output / "REGISTRY_TRANSACTION_REQUIREMENTS.json")
    transaction["expected_subject"]["model_id"] = "other-model"
    write_json(output / "REGISTRY_TRANSACTION_REQUIREMENTS.json", transaction)
    payloads = [
        path.name
        for path in output.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    ]
    write_evidence(output, payloads)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_authorization(output, signature_verifier=always_verify)
    assert exc_info.value.code == "TRANSACTION_SUBJECT_MISMATCH"


def test_extra_file_is_rejected(tmp_path: Path) -> None:
    output, _, _, _ = make_run(tmp_path)
    (output / "EXTRA.json").write_text("{}\n")
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_authorization(output, signature_verifier=always_verify)
    assert exc_info.value.code == "SHA256_COVERAGE_MISMATCH"


def test_cli_intent_prepare_and_finalize(tmp_path: Path, capsys) -> None:
    p17, signers, intent = make_intent(tmp_path)
    subject = tmp_path / "subject.json"
    policy = tmp_path / "policy.json"
    write_json(subject, intent.subject.model_dump(mode="json"))
    write_json(policy, intent.policy.model_dump(mode="json"))
    intent_path = tmp_path / "intent.json"
    assert (
        main(
            [
                "intent",
                "--p17",
                str(p17),
                "--subject",
                str(subject),
                "--policy",
                str(policy),
                "--allowed-signers",
                str(signers),
                "--run-id",
                intent.run_id,
                "--git-commit",
                intent.git_commit,
                "--requested-at-utc",
                intent.approval_requested_at_utc,
                "--expires-at-utc",
                intent.authorization_expires_at_utc,
                "--authorization-nonce",
                intent.authorization_nonce,
                "--output",
                str(intent_path),
            ]
        )
        == 0
    )
    owner_dir = tmp_path / "owner"
    assert (
        main(
            [
                "prepare-approval",
                "--intent",
                str(intent_path),
                "--role",
                "model_owner",
                "--approver-id",
                "owner@example",
                "--signer-identity",
                "owner@example",
                "--approved-at-utc",
                "2026-08-05T10:10:00Z",
                "--rationale",
                "Reviewed all prospective and evidence integrity requirements.",
                "--output-dir",
                str(owner_dir),
            ]
        )
        == 0
    )
    signature = owner_dir / "approval-signing-payload.bin.sig"
    signature.write_text(
        "-----BEGIN SSH SIGNATURE-----\nfake-signature-material\n-----END SSH SIGNATURE-----"
    )
    approval = owner_dir / "approval.json"
    assert (
        main(
            [
                "finalize-approval",
                "--draft",
                str(owner_dir / "approval-draft.json"),
                "--signature",
                str(signature),
                "--output",
                str(approval),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "PASS"


def test_cli_authorize_and_verify_with_injected_verifier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    p17, signers, intent = make_intent(tmp_path)
    approvals = make_approvals(intent)
    intent_path = tmp_path / "intent.json"
    write_json(intent_path, intent.model_dump(mode="json"))
    approval_paths = []
    for index, approval in enumerate(approvals):
        path = tmp_path / f"approval-{index}.json"
        write_json(path, approval.model_dump(mode="json"))
        approval_paths.append(path)
    monkeypatch.setattr(
        "loto.autogluon_campaign.approval_authorization_cli.make_ssh_signature_verifier",
        lambda _path: always_verify,
    )
    monkeypatch.setattr(
        authorization_module,
        "make_ssh_signature_verifier",
        lambda _path: always_verify,
    )
    output = tmp_path / "p18"
    assert (
        main(
            [
                "authorize",
                "--p17",
                str(p17),
                "--intent",
                str(intent_path),
                "--approval",
                str(approval_paths[0]),
                "--approval",
                str(approval_paths[1]),
                "--allowed-signers",
                str(signers),
                "--issued-at-utc",
                "2026-08-05T10:30:00Z",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert main(["verify", "--run", str(output)]) == 0


def test_cli_returns_two_for_invalid_input(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert main(["verify", "--run", str(missing)]) == 2
