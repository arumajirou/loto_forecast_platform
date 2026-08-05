from __future__ import annotations

import json
from pathlib import Path

from loto.neuralforecast.db_runtime_verification import evaluate_database_runtime_run

from db_runtime_fixture import make_run, write_json


def test_gpu_runtime_verification_requires_all_cuda_evidence(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1, require_gpu=True)

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=True)

    assert report.status == "PASS"
    assert report.model_results[0].runtime_status == "PASS"


def test_gpu_runtime_fails_without_training_worker_proof(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1, require_gpu=True)
    model_dir = run / "models" / "nf-auto-model-0"
    certification = json.loads(
        (model_dir / "runtime_certification.json").read_text(encoding="utf-8")
    )
    certification["formal_cuda_training_evidence"] = False
    certification["training_evidence"] = {}
    write_json(model_dir / "runtime_certification.json", certification)
    report_path = model_dir / "run_report.json"
    row = json.loads(report_path.read_text(encoding="utf-8"))
    row["runtime_certification"] = certification
    write_json(report_path, row)
    campaign_path = run / "campaign_report.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign["reports"][0] = row
    write_json(campaign_path, campaign)

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=True)

    assert report.status == "FAIL"
    failures = report.model_results[0].failures
    assert any("formal_training_cuda" in failure for failure in failures)
    assert any("training_evidence_present" in failure for failure in failures)


def test_search_space_tamper_is_detected(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1)
    profile_path = run / "models" / "nf-auto-model-0" / "SEARCH_SPACE_PROFILE.json"
    profile_path.write_text("{}\n", encoding="utf-8")

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=False)

    assert report.status == "FAIL"
    assert report.model_results[0].search_space_status == "FAIL"


def test_campaign_count_mismatch_is_fail_closed(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1)

    report = evaluate_database_runtime_run(run, expected_model_count=2, require_gpu=False)

    assert report.status == "FAIL"
    assert any("started_model_count mismatch" in failure for failure in report.failures)
    assert any("model row count mismatch" in failure for failure in report.failures)


def test_stochastic_runtime_requires_seeded_sample_artifacts(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1, stochastic_index=0)
    sample = run / "models" / "nf-auto-model-0" / "prediction_samples_after_load.csv"
    sample.unlink()

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=False)

    assert report.status == "FAIL"
    assert any(
        "prediction_samples_after_load.csv" in failure
        for failure in report.model_results[0].failures
    )


def test_gpu_override_rejects_cpu_campaign_plan(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1, require_gpu=False)

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=True)

    assert report.status == "FAIL"
    assert any("campaign plan does not require GPU" in failure for failure in report.failures)


def test_missing_run_directory_returns_structured_failure(tmp_path: Path) -> None:
    report = evaluate_database_runtime_run(tmp_path / "missing", expected_model_count=1)

    assert report.status == "FAIL"
    assert any("run directory is missing" in failure for failure in report.failures)


def test_invalid_expected_model_count_is_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1)

    report = evaluate_database_runtime_run(run, expected_model_count=0)

    assert report.status == "FAIL"
    assert "expected_model_count must be >= 1" in report.failures
