from __future__ import annotations

from pathlib import Path

from loto.autogluon_campaign.approval_authorization import (
    build_approval_intent,
    create_approval_authorization,
)
from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalPolicy,
    RegistrySubject,
)
from loto.autogluon_campaign.registry_transaction_contract import (
    RegistryTransactionRequest,
)
from loto.autogluon_campaign.registry_transaction_io import bootstrap_registry
from tests.autogluon_campaign.p18_test_support import (
    always_verify,
    make_allowed_signers,
    make_approvals,
    make_p17_bundle,
)


def registry_target(path: Path) -> str:
    return f"file+json://{path.absolute()}"


def make_subject(
    registry_path: Path,
    *,
    candidate_id: str = "TFT-known-past-static",
    revision: str = "0123456789abcdef",
) -> RegistrySubject:
    return RegistrySubject(
        registry_target=registry_target(registry_path),
        model_id="autogluon-timeseries-shadow",
        model_revision=revision,
        selected_candidate_id=candidate_id,
        model_artifact_sha256="1" * 64,
        data_snapshot_sha256="2" * 64,
        runtime_environment_sha256="3" * 64,
        code_sha256="4" * 64,
        config_sha256="5" * 64,
    )


def make_p18_bundle(
    tmp_path: Path,
    registry_path: Path,
    *,
    name: str = "p18",
    candidate_id: str = "TFT-known-past-static",
    revision: str = "0123456789abcdef",
    authorization_nonce: str = "a" * 64,
    requested_at: str = "2026-08-05T10:00:00Z",
    expires_at: str = "2026-08-05T11:00:00Z",
) -> Path:
    p17 = make_p17_bundle(
        tmp_path / f"{name}-p17",
        candidate_id=candidate_id,
    )
    signers = make_allowed_signers(tmp_path / f"{name}-allowed-signers")
    intent = build_approval_intent(
        p17_evidence_dir=p17,
        subject=make_subject(
            registry_path,
            candidate_id=candidate_id,
            revision=revision,
        ),
        policy=ApprovalPolicy(),
        allowed_signers_file=signers,
        run_id=f"{name}-approval",
        git_commit="0e17956cef83f7b8e866c16def361d8769f76ba7",
        requested_at_utc=requested_at,
        expires_at_utc=expires_at,
        authorization_nonce=authorization_nonce,
    )
    create_approval_authorization(
        p17_evidence_dir=p17,
        intent=intent,
        approvals=make_approvals(intent),
        allowed_signers_file=signers,
        output_dir=tmp_path / name,
        issued_at_utc="2026-08-05T10:30:00Z",
        signature_verifier=always_verify,
    )
    return tmp_path / name


def make_registry(tmp_path: Path) -> tuple[Path, str, str]:
    path = tmp_path / "registry" / "autogluon.json"
    path.parent.mkdir(parents=True)
    target = registry_target(path)
    state = bootstrap_registry(registry_path=path, registry_target=target)
    return path, target, state.state_sha256


def make_request(
    expected_state_sha256: str,
    *,
    run_id: str = "p19-register-20260805",
    transaction_nonce: str = "b" * 64,
    executed_at: str = "2026-08-05T10:40:00Z",
) -> RegistryTransactionRequest:
    return RegistryTransactionRequest(
        run_id=run_id,
        git_commit="4830d3d804134329303ffb75a38e5563ad6dfe15",
        expected_current_state_sha256=expected_state_sha256,
        transaction_nonce=transaction_nonce,
        executed_at_utc=executed_at,
    )
