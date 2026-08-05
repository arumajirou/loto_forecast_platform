from __future__ import annotations

import json
from pathlib import Path

from loto.models.neuralforecast_search_space import profile_fixed_config
from loto.models.neuralforecast_search_space_artifacts import persist_search_space_artifacts


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
