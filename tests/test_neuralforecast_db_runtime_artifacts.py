from __future__ import annotations

from pathlib import Path

from loto.neuralforecast.db_runtime_verification import (
    verify_sha256s,
    write_database_runtime_verification,
)

from db_runtime_fixture import make_run


def test_cpu_runtime_verification_writes_auditable_bundle(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    report = write_database_runtime_verification(
        run,
        expected_model_count=2,
        require_gpu=False,
    )

    assert report.status == "PASS"
    assert report.require_gpu is False
    assert all(model.status == "PASS" for model in report.model_results)
    assert (run / "VERIFICATION_REPORT.json").is_file()
    assert (run / "ARTIFACT_MANIFEST.json").is_file()
    assert (run / "RUNTIME_VERIFICATION_ENVIRONMENT.json").is_file()
    assert (run / "VERIFICATION_SUMMARY.txt").is_file()
    assert verify_sha256s(run) == []


def test_checksum_verifier_detects_post_verification_tamper(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1)
    report = write_database_runtime_verification(run, expected_model_count=1, require_gpu=False)
    assert report.status == "PASS"
    (run / "campaign_report.json").write_text("{}\n", encoding="utf-8")

    failures = verify_sha256s(run)

    assert any("campaign_report.json" in failure for failure in failures)
