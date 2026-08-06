from __future__ import annotations

from pathlib import Path

import pytest

from loto.provider_sandbox import (
    EffectiveSandboxEvidence,
    SandboxProcessRunner,
    VerificationStatus,
    build_argv_plan,
    verify_effective_evidence,
    verify_evidence_bundle,
    write_evidence_bundle,
)


def test_effective_match_verifies(policy, execution_request, effective) -> None:
    report = verify_effective_evidence(policy, execution_request, effective)
    assert report.status == VerificationStatus.VERIFIED
    assert report.verified is True


def test_missing_effective_evidence_is_incomplete(policy, execution_request, effective) -> None:
    values = effective.model_dump(mode="python", exclude={"evidence_sha256"})
    values["network_disabled"] = None
    incomplete = EffectiveSandboxEvidence.create(**values)
    report = verify_effective_evidence(policy, execution_request, incomplete)
    assert report.status == VerificationStatus.INCOMPLETE
    assert report.verified is False


def test_effective_mismatch_blocks(policy, execution_request, effective) -> None:
    values = effective.model_dump(mode="python", exclude={"evidence_sha256"})
    values["root_read_only"] = False
    mismatch = EffectiveSandboxEvidence.create(**values)
    report = verify_effective_evidence(policy, execution_request, mismatch)
    assert report.status == VerificationStatus.MISMATCH
    assert "root-read-only" in report.mismatches


def test_bundle_roundtrip_and_manifest_tamper(
    tmp_path: Path,
    policy,
    execution_request,
    backend,
    effective,
) -> None:
    plan = build_argv_plan(policy, execution_request, backend)
    verification = verify_effective_evidence(policy, execution_request, effective)
    process = SandboxProcessRunner().run(
        type(plan).create(
            backend=plan.backend,
            argv=("/usr/bin/true",),
            environment_keys=(),
        ),
        timeout_seconds=2,
        output_limit_bytes=1024,
    )
    bundle = tmp_path / "bundle"
    write_evidence_bundle(
        bundle,
        policy=policy,
        request=execution_request,
        backend=backend,
        plan=plan,
        effective=effective,
        verification=verification,
        process_result=process,
    )
    assert verify_evidence_bundle(bundle)["status"] == "PASS"
    (bundle / "request.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        verify_evidence_bundle(bundle)
