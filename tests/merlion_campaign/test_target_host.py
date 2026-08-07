from __future__ import annotations

import json
import pytest

from loto.merlion_campaign import target_host
from loto.merlion_campaign.certification import CertificationResult
from loto.merlion_campaign.protocol import ProviderResponse


class FakeAdapter:
    def __init__(self, command, timeout_seconds=120.0):
        self.command = command

    def run(self, request, work_root):
        if request.operation.value == "identity":
            evidence = {
                "package_name": "salesforce-merlion",
                "installed_version": "2.0.4",
                "version_match": True,
                "upstream_revision": target_host.EXPECTED_UPSTREAM_REVISION,
                "upstream_archived": True,
            }
        else:
            evidence = {
                "model_count": 3,
                "models": [{"model_name": name} for name in target_host.CORE_MODELS],
            }
        return ProviderResponse(
            request_id=request.request_id,
            status="PASS",
            phase=request.operation.value,
            message="ok",
            process_id=100,
            evidence=evidence,
        )


def fake_certify(command, request, work_root, timeout_seconds=120.0):
    model_dir = work_root / request.artifact_subdir
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}\n", encoding="utf-8")
    report = {
        "status": "RUNTIME_VERIFIED",
        "model_name": request.model_name,
        "train_process_id": 101,
        "load_process_id": 102,
        "prediction_match": True,
    }
    return CertificationResult(
        status="RUNTIME_VERIFIED",
        train_process_id=101,
        load_process_id=102,
        prediction_match=True,
        report_sha256="a" * 64,
        report=report,
    )


def test_target_host_success_and_offline_verification(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(target_host, "MerlionProviderAdapter", FakeAdapter)
    monkeypatch.setattr(target_host, "certify_core_model", fake_certify)
    output = tmp_path / "run"
    result = target_host.run_target_host_certification(
        ["provider"],
        output,
        expected_git_sha="b" * 40,
        lock_sha256="c" * 64,
    )
    assert result["status"] == "VERIFIED"
    assert result["source_status"] == "RUNTIME_CERTIFIED"
    report = json.loads((output / "VERIFICATION_REPORT.json").read_text())
    assert report["runtime_verified_models"] == ["Arima", "ETS", "MSES"]
    assert target_host.verify_target_host_run(output)["source_status"] == "RUNTIME_CERTIFIED"


def test_failure_is_published_as_valid_blocked_evidence(tmp_path, monkeypatch) -> None:
    class BrokenAdapter(FakeAdapter):
        def run(self, request, work_root):
            raise RuntimeError("package unavailable")

    monkeypatch.setattr(target_host, "MerlionProviderAdapter", BrokenAdapter)
    output = tmp_path / "blocked"
    result = target_host.run_target_host_certification(
        ["provider"],
        output,
        expected_git_sha="d" * 40,
        lock_sha256="e" * 64,
    )
    assert result["source_status"] == "BLOCKED"
    assert (output / "FAILURE.json").is_file()
    assert target_host.verify_target_host_run(output)["status"] == "VERIFIED"


def test_mutation_and_unlisted_file_are_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(target_host, "MerlionProviderAdapter", FakeAdapter)
    monkeypatch.setattr(target_host, "certify_core_model", fake_certify)
    output = tmp_path / "run"
    target_host.run_target_host_certification(
        ["provider"],
        output,
        expected_git_sha="f" * 40,
        lock_sha256="1" * 64,
    )
    (output / "VERIFICATION_REPORT.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(target_host.TargetHostError, match="SHA-256 mismatch"):
        target_host.verify_target_host_run(output)


def test_output_is_no_clobber(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(target_host, "MerlionProviderAdapter", FakeAdapter)
    monkeypatch.setattr(target_host, "certify_core_model", fake_certify)
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(target_host.TargetHostError, match="output already exists"):
        target_host.run_target_host_certification(
            ["provider"],
            output,
            expected_git_sha="2" * 40,
            lock_sha256="3" * 64,
        )
