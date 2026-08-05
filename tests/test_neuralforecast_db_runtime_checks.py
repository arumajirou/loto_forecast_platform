from __future__ import annotations

import json
from pathlib import Path

from loto.models.neuralforecast_search_space import profile_fixed_config
from loto.models.neuralforecast_search_space_artifacts import persist_search_space_artifacts
from loto.neuralforecast.db_runtime_verification import (
    evaluate_database_runtime_run,
    verify_sha256s,
    write_database_runtime_verification,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def runtime_certification(*, require_gpu: bool, stochastic: bool = False) -> dict:
    cuda_runtime = {
        "parameter_device": "cuda:0",
        "trainer_root_device": "cuda:0",
        "cuda_memory_allocated": 1024,
        "cuda_memory_reserved": 2048,
        "cuda_peak_memory_allocated": 4096,
    }
    cpu_runtime = {
        "parameter_device": "cpu",
        "trainer_root_device": "cpu",
        "cuda_memory_allocated": 0,
        "cuda_memory_reserved": 0,
        "cuda_peak_memory_allocated": 0,
    }
    runtime = cuda_runtime if require_gpu else cpu_runtime
    gpu = {"gpu_pid_verified": require_gpu, "pid": 1234 if require_gpu else None}
    return {
        "schema_version": "1.2.0",
        "status": "PASS",
        "loaded": True,
        "predicted": True,
        "shape_match": True,
        "key_match": True,
        "finite": True,
        "prediction_match": True,
        "state_before_finite": True,
        "state_after_finite": True,
        "prediction_policy": "stochastic" if stochastic else "deterministic",
        "require_gpu": require_gpu,
        "training_evidence": (
            {"formal_training_proof": True, "cuda_execution_evidence": True}
            if require_gpu
            else {}
        ),
        "formal_cuda_training_evidence": require_gpu,
        "cuda_pre_save_inference_evidence": require_gpu,
        "cuda_reload_inference_evidence": require_gpu,
        "cuda_execution_evidence": require_gpu,
        "cpu_fallback": False,
        "runtime_pre_save_inference": runtime,
        "runtime_reload_inference": runtime,
        "gpu_pre_save_inference": gpu,
        "gpu_reload_inference": gpu,
        "failed_checks": [],
    }


def make_run(
    tmp_path: Path,
    *,
    model_count: int = 2,
    require_gpu: bool = False,
    stochastic_index: int | None = None,
) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "input_panel.csv").write_text("unique_id,ds,y\na,1,1\n", encoding="utf-8")
    models = []
    reports = []
    for index in range(model_count):
        model_id = f"nf-auto-model-{index}"
        class_name = f"AutoModel{index}"
        models.append({"model_id": model_id, "class_name": class_name})
        model_dir = run / "models" / model_id
        model_dir.mkdir(parents=True)
        profile = profile_fixed_config(
            {"input_size": 12, "random_seed": 1},
            backend="optuna",
            model_name=class_name,
        )
        artifacts = persist_search_space_artifacts(
            model_dir,
            profile,
            context={"phase": "runtime_resolved", "model_id": model_id},
        )
        evidence = {
            "schema_version": "1.0.0",
            "phase": "runtime_resolved",
            "profile": profile.model_dump(mode="json"),
            "artifacts": artifacts,
        }
        certification = runtime_certification(
            require_gpu=require_gpu,
            stochastic=index == stochastic_index,
        )
        for name in ("predictions.csv", "prediction_after_load.csv"):
            (model_dir / name).write_text(
                "unique_id,ds,prediction\na,2,1\n",
                encoding="utf-8",
            )
        if certification["prediction_policy"] == "stochastic":
            for name in (
                "prediction_samples_before_save.csv",
                "prediction_samples_after_load.csv",
            ):
                (model_dir / name).write_text(
                    "unique_id,ds,prediction,sample_index,seed\na,2,1,0,1\n",
                    encoding="utf-8",
                )
        write_json(model_dir / "runtime_certification.json", certification)
        row = {
            "model_id": model_id,
            "class_name": class_name,
            "status": "SUCCEEDED",
            "certification_status": "RUNTIME_CERTIFIED",
            "runtime_certification": certification,
            "search_space_evidence": evidence,
        }
        write_json(model_dir / "run_report.json", row)
        reports.append(row)

    write_json(
        run / "campaign_plan.json",
        {
            "schema_version": "1.1.0",
            "models": models,
            "runtime_certification": {"require_gpu_execution": require_gpu},
        },
    )
    write_json(
        run / "campaign_report.json",
        {
            "schema_version": "1.1.0",
            "status": "SUCCEEDED",
            "certification_status": "RUNTIME_CERTIFIED",
            "started_model_count": model_count,
            "succeeded_model_count": model_count,
            "runtime_certified_model_count": model_count,
            "failed_model_count": 0,
            "search_space_artifact_status": "PASS",
            "search_space_verified_model_count": model_count,
            "reports": reports,
        },
    )
    return run


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


def test_cpu_override_rejects_gpu_campaign_plan(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1, require_gpu=True)

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=False)

    assert report.status == "FAIL"
    assert any("campaign plan requires GPU" in failure for failure in report.failures)


def test_campaign_row_and_model_report_must_match(tmp_path: Path) -> None:
    run = make_run(tmp_path, model_count=1)
    model_report = run / "models" / "nf-auto-model-0" / "run_report.json"
    payload = json.loads(model_report.read_text(encoding="utf-8"))
    payload["point_column"] = "tampered"
    write_json(model_report, payload)

    report = evaluate_database_runtime_run(run, expected_model_count=1, require_gpu=False)

    assert report.status == "FAIL"
    assert any(
        "campaign row/model run_report mismatch" in failure
        for failure in report.model_results[0].failures
    )
