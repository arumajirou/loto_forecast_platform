from __future__ import annotations

import json
from pathlib import Path

import pytest
from p11_helpers import build_request, fake_verifier

from loto.sktime_campaign.primary_promotion_artifacts import (
    P11VerificationError,
    persist_p11,
    verify_p11,
)


def persist(tmp_path: Path):
    request = build_request(tmp_path)
    response = persist_p11(
        request,
        issued_at_utc="2026-08-05T10:25:00Z",
        signature_verifier=fake_verifier,
    )
    return request, response, Path(request.output_dir)


def test_persist_and_verify_success(tmp_path):
    request, response, output_dir = persist(tmp_path)
    assert response["decision"] == ("AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION")
    result = verify_p11(output_dir, request)
    assert result["status"] == "PASS"
    assert result["primary_promotion_executed"] is False


def test_output_directory_must_be_empty(tmp_path):
    request = build_request(tmp_path)
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True)
    (output_dir / "unexpected").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="must be empty"):
        persist_p11(
            request,
            issued_at_utc="2026-08-05T10:25:00Z",
            signature_verifier=fake_verifier,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "P10_LINEAGE.json",
        "DEPLOYMENT_PRECONDITION.json",
        "PRIMARY_PROMOTION_INTENT.json",
        "APPROVALS.json",
        "PRIMARY_PROMOTION_AUTHORIZATION.json",
        "P12_TRANSACTION_REQUIREMENTS.json",
        "ROLLBACK_AND_MONITORING_PLAN.json",
        "response.json",
    ],
)
def test_tamper_detected(tmp_path, filename):
    request, _, output_dir = persist(tmp_path)
    path = output_dir / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload[0]["tampered"] = True
    else:
        payload["tampered"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P11VerificationError):
        verify_p11(output_dir, request)


def test_manifest_coverage_tamper_detected(tmp_path):
    request, _, output_dir = persist(tmp_path)
    manifest_path = output_dir / "ARTIFACT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = manifest["files"][:-1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(P11VerificationError):
        verify_p11(output_dir, request)


def test_sha256sums_tamper_detected(tmp_path):
    request, _, output_dir = persist(tmp_path)
    path = output_dir / "SHA256SUMS"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(P11VerificationError):
        verify_p11(output_dir, request)


def test_signature_verification_evidence_tamper_detected(tmp_path):
    request, _, output_dir = persist(tmp_path)
    path = output_dir / "SIGNATURE_VERIFICATION.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[0]["verified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P11VerificationError):
        verify_p11(output_dir, request)


def test_response_forbidden_field_tamper_detected(tmp_path):
    request, _, output_dir = persist(tmp_path)
    path = output_dir / "response.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["primary_binding_changed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P11VerificationError):
        verify_p11(output_dir, request)
