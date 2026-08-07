from __future__ import annotations

import json

import pytest

from loto.sktime_campaign.canary_evaluation_artifacts import (
    P10VerificationError,
    persist_p10,
    verify_p10,
)
from p10_helpers import make_request


def test_persist_and_verify_complete_bundle(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    response = persist_p10(request)
    assert response["decision"] == "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW"
    verify_p10(request, tmp_path / "evidence")


def test_output_directory_must_be_empty(tmp_path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "existing").write_text("x")
    with pytest.raises(RuntimeError, match="must be empty"):
        persist_p10(make_request(output))


def test_window_metric_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    path = tmp_path / "evidence" / "WINDOW_METRICS.json"
    payload = json.loads(path.read_text())
    payload[0]["hit_at_1"] = 0.0
    path.write_text(json.dumps(payload))
    with pytest.raises(P10VerificationError):
        verify_p10(request, tmp_path / "evidence")


def test_decision_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    path = tmp_path / "evidence" / "PRIMARY_PROMOTION_REVIEW_DECISION.json"
    payload = json.loads(path.read_text())
    payload["primary_promotion_executed"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(P10VerificationError):
        verify_p10(request, tmp_path / "evidence")


def test_lineage_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    path = tmp_path / "evidence" / "P9_LINEAGE.json"
    payload = json.loads(path.read_text())
    payload["activation_id"] = "9" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(P10VerificationError):
        verify_p10(request, tmp_path / "evidence")


def test_manifest_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    path = tmp_path / "evidence" / "ARTIFACT_MANIFEST.json"
    payload = json.loads(path.read_text())
    payload["scope"] = "wrong"
    path.write_text(json.dumps(payload))
    with pytest.raises(P10VerificationError):
        verify_p10(request, tmp_path / "evidence")


def test_sha_coverage_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    path = tmp_path / "evidence" / "SHA256SUMS"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(P10VerificationError, match="coverage"):
        verify_p10(request, tmp_path / "evidence")


def test_extra_file_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "evidence")
    persist_p10(request)
    (tmp_path / "evidence" / "EXTRA.txt").write_text("unexpected")
    with pytest.raises(P10VerificationError):
        verify_p10(request, tmp_path / "evidence")
