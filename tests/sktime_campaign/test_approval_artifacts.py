from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.approval_artifacts import (
    P7VerificationError,
    persist_p7,
    verify_p7,
)
from test_approval_authorization import ISSUED, make_request, verifier


def _rewrite(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_persist_and_verify_p7(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    response = persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    assert response["registry_write_authorized"] is True
    assert response["registry_write_executed"] is False
    verification = verify_p7(
        Path(request.output_dir),
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    assert verification["status"] == "PASS"
    assert verification["promotion_status"] == "APPROVED_NOT_REGISTERED"


def test_output_directory_must_be_empty(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "existing.txt").write_text("occupied", encoding="utf-8")
    request = make_request(output_dir=str(output))
    with pytest.raises(RuntimeError, match="must be empty"):
        persist_p7(
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_tampered_authorization_is_rejected(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "REGISTRY_AUTHORIZATION.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["subject"]["model_id"] = "tampered"
    _rewrite(path, payload)
    with pytest.raises(P7VerificationError, match="authorization mismatch"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_tampered_p6_lineage_is_rejected(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "P6_LINEAGE.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["p6_run_id"] = "tampered"
    _rewrite(path, payload)
    with pytest.raises(P7VerificationError, match="P6 lineage"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_tampered_signature_evidence_is_rejected(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "SIGNATURE_VERIFICATION.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[0]["signature_verification_status"] = "FAILED"
    _rewrite(path, payload)
    with pytest.raises(P7VerificationError, match="signature verification"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_response_cannot_claim_registry_write(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "response.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["registry_write_executed"] = True
    _rewrite(path, payload)
    with pytest.raises(P7VerificationError, match="incorrectly claims write"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "ARTIFACT_MANIFEST.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scope"] = "wrong"
    _rewrite(path, payload)
    with pytest.raises(P7VerificationError, match="manifest scope"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_sha256sums_tampering_is_rejected(tmp_path: Path) -> None:
    request = make_request(output_dir=str(tmp_path / "evidence"))
    persist_p7(
        request,
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    path = Path(request.output_dir) / "SHA256SUMS"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = "0" * 64 + lines[0][64:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(P7VerificationError, match="SHA-256 mismatch"):
        verify_p7(
            Path(request.output_dir),
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )
