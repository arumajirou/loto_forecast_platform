from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.holdout_artifacts import (
    P4VerificationError,
    persist_p4,
    verify_p4,
)
from test_holdout_scoring import _lock, _request


def test_persist_and_verify_p4_bundle(tmp_path: Path):
    lock = _lock()
    request = _request(lock).model_copy(
        update={"output_dir": str(tmp_path / "p4")}
    )
    response = persist_p4(request, lock)
    assert response["status"] == "PASS"
    report = verify_p4(Path(request.output_dir), request, lock)
    assert report["status"] == "PASS"
    assert report["model_execution"] is False


def test_p4_bundle_contains_expected_files(tmp_path: Path):
    lock = _lock()
    request = _request(lock).model_copy(
        update={"output_dir": str(tmp_path / "p4")}
    )
    persist_p4(request, lock)
    names = {path.name for path in Path(request.output_dir).iterdir()}
    assert names == {
        "REQUEST_METADATA.json",
        "P3_LINEAGE.json",
        "HOLDOUT_ACTUALS.json",
        "HOLDOUT_RESULTS.json",
        "HOLDOUT_CANDIDATE_AGGREGATES.json",
        "HOLDOUT_LEADERBOARD.json",
        "BASELINE_COMPARISON.json",
        "response.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }


def test_verifier_detects_metric_tampering(tmp_path: Path):
    lock = _lock()
    request = _request(lock).model_copy(
        update={"output_dir": str(tmp_path / "p4")}
    )
    persist_p4(request, lock)
    path = Path(request.output_dir) / "HOLDOUT_RESULTS.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["metrics"]["hit_at_1"] = 0.123
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(P4VerificationError):
        verify_p4(Path(request.output_dir), request, lock)


def test_verifier_detects_lineage_tampering(tmp_path: Path):
    lock = _lock()
    request = _request(lock).model_copy(
        update={"output_dir": str(tmp_path / "p4")}
    )
    persist_p4(request, lock)
    path = Path(request.output_dir) / "P3_LINEAGE.json"
    lineage = json.loads(path.read_text(encoding="utf-8"))
    lineage["lock_seal_sha256"] = "0" * 64
    path.write_text(json.dumps(lineage), encoding="utf-8")
    with pytest.raises(P4VerificationError):
        verify_p4(Path(request.output_dir), request, lock)


def test_verifier_detects_actual_tampering(tmp_path: Path):
    lock = _lock()
    request = _request(lock).model_copy(
        update={"output_dir": str(tmp_path / "p4")}
    )
    persist_p4(request, lock)
    path = Path(request.output_dir) / "HOLDOUT_ACTUALS.json"
    actuals = json.loads(path.read_text(encoding="utf-8"))
    actuals["values"][0][0] += 1
    path.write_text(json.dumps(actuals), encoding="utf-8")
    with pytest.raises(P4VerificationError):
        verify_p4(Path(request.output_dir), request, lock)


def test_nonempty_output_directory_is_rejected(tmp_path: Path):
    lock = _lock()
    output = tmp_path / "p4"
    output.mkdir()
    (output / "existing.txt").write_text("x", encoding="utf-8")
    request = _request(lock).model_copy(update={"output_dir": str(output)})
    with pytest.raises(RuntimeError, match="empty"):
        persist_p4(request, lock)
