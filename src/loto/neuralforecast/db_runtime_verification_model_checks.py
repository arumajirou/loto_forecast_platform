"""Per-model runtime and search-space checks for database campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from loto.models.neuralforecast_search_space_artifacts import (
    MANIFEST_NAME,
    MANIFEST_SUM_NAME,
    PROFILE_NAME,
    PROFILE_SUM_NAME,
    verify_search_space_artifacts,
)

from .db_runtime_verification_models import ModelRuntimeVerification


def _cuda_device(snapshot: Mapping[str, Any]) -> bool:
    return bool(
        str(snapshot.get("parameter_device") or "").startswith("cuda")
        or str(snapshot.get("trainer_root_device") or "").startswith("cuda")
    )


def _vram_evidence(snapshot: Mapping[str, Any]) -> bool:
    for key in (
        "cuda_memory_allocated",
        "cuda_memory_reserved",
        "cuda_peak_memory_allocated",
    ):
        try:
            if float(snapshot.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def runtime_failures(
    certification: Mapping[str, Any],
    *,
    require_gpu: bool,
) -> list[str]:
    checks: dict[str, bool] = {
        "status": certification.get("status") == "PASS",
        "loaded": certification.get("loaded") is True,
        "predicted": certification.get("predicted") is True,
        "shape_match": certification.get("shape_match") is True,
        "key_match": certification.get("key_match") is True,
        "finite": certification.get("finite") is True,
        "prediction_match": certification.get("prediction_match") is True,
        "state_before_finite": certification.get("state_before_finite") is True,
        "state_after_finite": certification.get("state_after_finite") is True,
        "no_failed_checks": not certification.get("failed_checks"),
        "no_cpu_fallback": certification.get("cpu_fallback") is False,
    }
    if require_gpu:
        runtime_pre = certification.get("runtime_pre_save_inference")
        runtime_reload = certification.get("runtime_reload_inference")
        gpu_pre = certification.get("gpu_pre_save_inference")
        gpu_reload = certification.get("gpu_reload_inference")
        checks.update(
            {
                "require_gpu": certification.get("require_gpu") is True,
                "training_evidence_present": bool(certification.get("training_evidence")),
                "formal_training_cuda": (
                    certification.get("formal_cuda_training_evidence") is True
                ),
                "pre_save_cuda": (
                    certification.get("cuda_pre_save_inference_evidence") is True
                ),
                "reload_cuda": (
                    certification.get("cuda_reload_inference_evidence") is True
                ),
                "combined_cuda": certification.get("cuda_execution_evidence") is True,
                "pre_save_device_cuda": (
                    isinstance(runtime_pre, Mapping) and _cuda_device(runtime_pre)
                ),
                "reload_device_cuda": (
                    isinstance(runtime_reload, Mapping) and _cuda_device(runtime_reload)
                ),
                "pre_save_vram": (
                    isinstance(runtime_pre, Mapping) and _vram_evidence(runtime_pre)
                ),
                "reload_vram": (
                    isinstance(runtime_reload, Mapping) and _vram_evidence(runtime_reload)
                ),
                "pre_save_gpu_pid": (
                    isinstance(gpu_pre, Mapping) and gpu_pre.get("gpu_pid_verified") is True
                ),
                "reload_gpu_pid": (
                    isinstance(gpu_reload, Mapping)
                    and gpu_reload.get("gpu_pid_verified") is True
                ),
            }
        )
    return sorted(name for name, passed in checks.items() if not passed)


def _critical_model_paths(model_dir: Path, certification: Mapping[str, Any]) -> list[Path]:
    paths = [
        model_dir / "run_report.json",
        model_dir / "runtime_certification.json",
        model_dir / "predictions.csv",
        model_dir / "prediction_after_load.csv",
        model_dir / PROFILE_NAME,
        model_dir / PROFILE_SUM_NAME,
        model_dir / MANIFEST_NAME,
        model_dir / MANIFEST_SUM_NAME,
    ]
    if certification.get("prediction_policy") == "stochastic":
        paths.extend(
            [
                model_dir / "prediction_samples_before_save.csv",
                model_dir / "prediction_samples_after_load.csv",
            ]
        )
    return paths


def verify_model(
    run_dir: Path,
    row: Mapping[str, Any],
    *,
    require_gpu: bool,
    read_json_object: Callable[[Path, list[str], str], dict[str, Any]],
    sha256_file: Callable[[Path], str],
) -> ModelRuntimeVerification:
    model_id = str(row.get("model_id") or "").strip()
    class_name = str(row.get("class_name") or "").strip() or None
    failures: list[str] = []
    if not model_id:
        model_id = "<missing-model-id>"
        failures.append("model_id is missing")
    model_dir = run_dir / "models" / model_id
    report = read_json_object(model_dir / "run_report.json", failures, "model run report")
    if report and report.get("model_id") != row.get("model_id"):
        failures.append("campaign/model run_report model_id mismatch")
    if row.get("status") != "SUCCEEDED":
        failures.append(f"model status is not SUCCEEDED: {row.get('status')}")
    if row.get("certification_status") != "RUNTIME_CERTIFIED":
        failures.append(
            "model certification_status is not RUNTIME_CERTIFIED: "
            f"{row.get('certification_status')}"
        )

    search_verification = verify_search_space_artifacts(model_dir)
    if search_verification.get("status") != "PASS":
        failures.append(f"search-space artifacts failed: {search_verification}")
    evidence = report.get("search_space_evidence") if report else None
    profile_sha256: str | None = None
    if not isinstance(evidence, Mapping):
        failures.append("run_report search_space_evidence is missing")
    else:
        profile = evidence.get("profile")
        artifacts = evidence.get("artifacts")
        if isinstance(profile, Mapping):
            profile_sha256 = str(profile.get("profile_sha256") or "") or None
        if not isinstance(artifacts, Mapping):
            failures.append("run_report search_space artifacts are missing")
        elif artifacts.get("verification_status") != "PASS":
            failures.append("run_report search-space verification_status is not PASS")

    certification_path = model_dir / "runtime_certification.json"
    certification = read_json_object(
        certification_path,
        failures,
        "runtime certification",
    )
    embedded = row.get("runtime_certification")
    if not isinstance(embedded, Mapping):
        failures.append("campaign row runtime_certification is missing")
    elif certification and dict(embedded) != certification:
        failures.append("campaign row/runtime_certification.json mismatch")
    failed = runtime_failures(certification, require_gpu=require_gpu) if certification else []
    failures.extend(f"runtime check failed: {name}" for name in failed)

    critical_paths = _critical_model_paths(model_dir, certification)
    missing = [path.name for path in critical_paths if not path.is_file()]
    if missing:
        failures.append(f"critical model artifacts missing: {sorted(missing)}")
    relative_artifacts = tuple(
        path.relative_to(run_dir).as_posix() for path in critical_paths if path.is_file()
    )
    return ModelRuntimeVerification(
        model_id=model_id,
        class_name=class_name,
        status="PASS" if not failures else "FAIL",
        model_status=str(row.get("status") or "") or None,
        certification_status=str(row.get("certification_status") or "") or None,
        search_space_status=str(search_verification.get("status") or "FAIL"),
        runtime_status=str(certification.get("status") or "FAIL"),
        profile_sha256=profile_sha256,
        runtime_certification_sha256=(
            sha256_file(certification_path) if certification_path.is_file() else None
        ),
        critical_artifacts=relative_artifacts,
        failures=tuple(failures),
    )
