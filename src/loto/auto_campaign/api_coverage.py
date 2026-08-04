from __future__ import annotations

import json
import shutil
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import CampaignConfig, CoverageStatus
from .data_tracks import build_panel, load_miniloto, pre_holdout_frame
from .metrics import select_point_column
from .model_factory import build_auto_model
from .persistence import finite_state_dict, sha256_file, write_json, write_sha256s
from .runtime import gpu_process_snapshot, torch_runtime_snapshot


@dataclass(frozen=True)
class ApiCase:
    case_id: str
    layer: str
    argument: str
    value: str
    expected: str = "PASS"


@dataclass
class ApiCaseResult:
    case: ApiCase
    status: str
    started_at: str
    finished_at: str
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None
    artifacts: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"case": asdict(self.case), **{k: v for k, v in asdict(self).items() if k != "case"}}


def api_case_plan() -> list[ApiCase]:
    cases = [
        ApiCase("base-h-5", "BaseAuto", "h", "5"),
        ApiCase("base-loss-mse", "BaseAuto", "loss", "MSE"),
        ApiCase("base-valid-loss-mse", "BaseAuto", "valid_loss", "MSE"),
        ApiCase("base-time-budget", "BaseAuto", "time_budget", "30"),
        ApiCase("base-num-samples-30", "BaseAuto", "num_samples", "30"),
        ApiCase(
            "base-search-alg-seed-2026",
            "BaseAuto",
            "search_alg",
            "BasicVariantGenerator(random_state=2026)",
        ),
        ApiCase("base-refit-with-val", "BaseAuto", "refit_with_val", "true"),
        ApiCase("base-verbose", "BaseAuto", "verbose", "true"),
        ApiCase("base-alias-none", "BaseAuto", "alias", "None"),
        ApiCase("base-backend-optuna", "BaseAuto", "backend", "optuna"),
        ApiCase("base-callbacks-optuna", "BaseAuto", "callbacks", "optuna callback"),
        ApiCase("base-ray-options-none", "BaseAuto", "ray_options", "None"),
        ApiCase("base-optuna-options-none", "BaseAuto", "optuna_options", "None"),
        ApiCase("base-cpus-rejected", "BaseAuto", "cpus", "1", "EXPECTED_ERROR"),
        ApiCase("base-gpus-rejected", "BaseAuto", "gpus", "1", "EXPECTED_ERROR"),
        ApiCase("nf-multiple-models", "NeuralForecast", "models", "2 AutoMLP"),
        ApiCase("nf-invalid-freq", "NeuralForecast", "freq", "invalid", "EXPECTED_ERROR"),
    ]
    for scaler in ("standard", "robust", "robust-iqr", "minmax", "boxcox"):
        cases.append(
            ApiCase(
                f"nf-local-scaler-{scaler}",
                "NeuralForecast",
                "local_scaler_type",
                scaler,
            )
        )
    for scaler in ("standard", "robust", "robust-iqr", "minmax", "boxcox"):
        cases.append(
            ApiCase(
                f"nf-static-scaler-{scaler}",
                "NeuralForecast",
                "local_static_scaler_type",
                scaler,
            )
        )
    cases.extend(
        [
            ApiCase("fit-df-none", "fit", "df", "None with stored dataset"),
            ApiCase("fit-static-df", "fit", "static_df", "synthetic static"),
            ApiCase("fit-explicit-val-df", "fit", "val_df", "explicit validation"),
            ApiCase("fit-use-init-models", "fit", "use_init_models", "true"),
            ApiCase("fit-verbose", "fit", "verbose", "true"),
            ApiCase("fit-alt-id-col", "fit", "id_col", "series_id"),
            ApiCase("fit-alt-time-col", "fit", "time_col", "time_index"),
            ApiCase("fit-alt-target-col", "fit", "target_col", "target"),
            ApiCase(
                "fit-distributed-config",
                "fit",
                "distributed_config",
                "Spark contract",
                "NOT_APPLICABLE",
            ),
            ApiCase("fit-prediction-intervals", "fit", "prediction_intervals", "conformal"),
        ]
    )
    return cases


def _case_config(
    config: CampaignConfig,
    case: ApiCase,
    root: Path,
) -> CampaignConfig:
    update: dict[str, Any] = {
        "h": 5 if case.case_id == "base-h-5" else 1,
        "max_steps_smoke": 1,
        "val_check_steps_smoke": 1,
    }
    search = config.search
    extra: dict[str, Any] = {}
    if case.case_id == "base-time-budget":
        search = search.model_copy(update={"time_budget": 30})
    elif case.case_id == "base-num-samples-30":
        search = search.model_copy(update={"num_samples": 30})
    elif case.case_id == "base-search-alg-seed-2026":
        search = search.model_copy(update={"search_seed": 2026})
    elif case.case_id == "base-refit-with-val":
        search = search.model_copy(update={"refit_with_val": True})
    elif case.case_id == "base-verbose":
        search = search.model_copy(update={"verbose": True})
    elif case.case_id == "base-alias-none":
        extra["alias"] = None
    elif case.case_id == "base-ray-options-none":
        extra["ray_options"] = None
    elif case.case_id == "base-optuna-options-none":
        extra["optuna_options"] = None
    elif case.case_id == "base-callbacks-optuna":
        marker = root / "callback_invocations.jsonl"

        def callback(_study: Any, trial: Any) -> None:
            with marker.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "trial_number": trial.number,
                            "state": str(trial.state),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

        extra["callbacks"] = [callback]
    if case.case_id in {"base-loss-mse", "base-valid-loss-mse"}:
        from neuralforecast.losses.pytorch import MSE

        if case.case_id == "base-loss-mse":
            extra["loss"] = MSE()
        else:
            extra["valid_loss"] = MSE()
    update["search"] = search
    update["extra_base_auto_args"] = extra
    return config.model_copy(update=update)


def _build_models(
    *,
    case: ApiCase,
    config: CampaignConfig,
    root: Path,
    count: int = 1,
):
    backend = (
        "optuna"
        if case.case_id
        in {
            "base-backend-optuna",
            "base-optuna-options-none",
            "base-callbacks-optuna",
        }
        else "ray"
    )
    models = []
    for index in range(count):
        alias = None if case.case_id == "base-alias-none" else f"api_{case.case_id}_{index}"
        model, _requested, _kwargs = build_auto_model(
            model_name="AutoMLP",
            config=config,
            backend=backend,
            alias=alias or f"AutoMLP_api_{index}",
            trial_root=root / f"trial_work_{index}",
            n_series=None,
            num_samples=(30 if case.case_id == "base-num-samples-30" else 1),
            seed=1 + index,
            smoke=True,
            fixed_config=None,
        )
        if case.case_id == "base-alias-none":
            model.alias = None
        models.append(model)
    return models


def _expected_resource_error(case: ApiCase, config: CampaignConfig) -> None:
    from neuralforecast.auto import AutoMLP

    fixed = {
        "input_size": 2,
        "hidden_size": 16,
        "num_layers": 1,
        "learning_rate": 1e-3,
        "scaler_type": "identity",
        "max_steps": 1,
        "batch_size": 1,
        "windows_batch_size": 8,
        "random_seed": 1,
    }
    kwargs: dict[str, Any] = {
        "h": config.h,
        "config": fixed,
        "backend": "ray",
        "num_samples": 1,
    }
    kwargs[case.argument] = 1
    try:
        AutoMLP(**kwargs)
    except TypeError:
        return
    raise AssertionError(f"{case.argument}=1 was not rejected by NeuralForecast 3.2.0")


def _fit_case(case: ApiCase, config: CampaignConfig, root: Path) -> dict[str, Any]:
    if case.expected == "NOT_APPLICABLE":
        return {
            "status": CoverageStatus.NOT_APPLICABLE.value,
            "reason": "Spark runtime is not part of the local GPU campaign",
        }
    if case.case_id in {"base-cpus-rejected", "base-gpus-rejected"}:
        _expected_resource_error(case, config)
        return {"status": CoverageStatus.UNSUPPORTED_BY_VERSION.value}

    frame, contract = load_miniloto(config)
    training = pre_holdout_frame(frame, config)
    panel = build_panel(training, contract, track="u_shared")
    data = panel[["unique_id", "ds", "y"]].copy()
    case_config = _case_config(config, case, root)
    model_count = 2 if case.case_id == "nf-multiple-models" else 1
    models = _build_models(case=case, config=case_config, root=root, count=model_count)

    from neuralforecast import NeuralForecast

    nf_kwargs: dict[str, Any] = {
        "models": models,
        "freq": 1,
        "local_scaler_type": None,
        "local_static_scaler_type": None,
    }
    static_df: pd.DataFrame | None = None
    if case.case_id.startswith("nf-local-scaler-"):
        nf_kwargs["local_scaler_type"] = case.value
    if case.case_id.startswith("nf-static-scaler-"):
        nf_kwargs["local_static_scaler_type"] = case.value
        static_df = pd.DataFrame(
            {
                "unique_id": sorted(data["unique_id"].unique()),
                "static_value": np.arange(1, data["unique_id"].nunique() + 1, dtype=float),
            }
        )
    if case.case_id == "nf-invalid-freq":
        nf_kwargs["freq"] = "definitely-invalid"

    nf = NeuralForecast(**nf_kwargs)
    val_size = min(5, max(1, training.shape[0] // 10))
    fit_data = data
    fit_kwargs: dict[str, Any] = {
        "df": fit_data,
        "static_df": static_df,
        "val_size": val_size,
        "val_df": None,
        "use_init_models": False,
        "verbose": case.case_id == "fit-verbose",
        "id_col": "unique_id",
        "time_col": "ds",
        "target_col": "y",
        "distributed_config": None,
        "prediction_intervals": None,
    }

    if case.case_id == "fit-explicit-val-df":
        split = data.groupby("unique_id", sort=False).tail(val_size).index
        fit_kwargs["val_df"] = data.loc[split].copy()
        fit_kwargs["df"] = data.drop(index=split).copy()
        fit_kwargs["val_size"] = 0
    elif case.case_id == "fit-use-init-models":
        fit_kwargs["use_init_models"] = True
    elif case.case_id in {"fit-alt-id-col", "fit-alt-time-col", "fit-alt-target-col"}:
        renames = {
            "fit-alt-id-col": {"unique_id": "series_id"},
            "fit-alt-time-col": {"ds": "time_index"},
            "fit-alt-target-col": {"y": "target"},
        }[case.case_id]
        fit_kwargs["df"] = data.rename(columns=renames)
        fit_kwargs["id_col"] = next(
            (value for key, value in renames.items() if key == "unique_id"),
            "unique_id",
        )
        fit_kwargs["time_col"] = next(
            (value for key, value in renames.items() if key == "ds"),
            "ds",
        )
        fit_kwargs["target_col"] = next(
            (value for key, value in renames.items() if key == "y"),
            "y",
        )
    elif case.case_id == "fit-prediction-intervals":
        from neuralforecast.utils import PredictionIntervals

        fit_kwargs["prediction_intervals"] = PredictionIntervals(
            n_windows=2,
            method="conformal_distribution",
        )

    if case.expected == "EXPECTED_ERROR":
        try:
            nf.fit(**fit_kwargs)
        except Exception:
            return {"status": CoverageStatus.EXECUTED.value, "expected_error": True}
        raise AssertionError(f"case did not raise expected error: {case.case_id}")

    nf.fit(**fit_kwargs)
    if case.case_id == "base-callbacks-optuna":
        marker = root / "callback_invocations.jsonl"
        if not marker.is_file() or not marker.read_text(encoding="utf-8").strip():
            raise RuntimeError("Optuna callback was not invoked")
    if case.case_id == "fit-df-none":
        nf.fit(
            df=None,
            val_size=val_size,
            use_init_models=True,
            verbose=False,
        )
    prediction_before = nf.predict()
    point_columns = [select_point_column(prediction_before, str(model)) for model in models]
    for column in point_columns:
        if not np.isfinite(prediction_before[column].to_numpy(dtype=float)).all():
            raise RuntimeError(f"non-finite prediction column: {column}")

    save_path = root / "neuralforecast"
    nf.save(str(save_path), save_dataset=True, overwrite=True)
    loaded = NeuralForecast.load(str(save_path))
    prediction_after = loaded.predict()
    for before_column, model in zip(point_columns, models, strict=True):
        after_column = select_point_column(prediction_after, str(model))
        if not np.allclose(
            prediction_before[before_column].to_numpy(dtype=float),
            prediction_after[after_column].to_numpy(dtype=float),
            rtol=1e-6,
            atol=1e-6,
        ):
            raise RuntimeError("prediction changed after load")

    prediction_before.to_parquet(root / "prediction_before.parquet", index=False)
    prediction_after.to_parquet(root / "prediction_after.parquet", index=False)
    runtimes = [torch_runtime_snapshot(getattr(model, "model", None)) for model in models]
    state_finite = all(finite_state_dict(getattr(model, "model", None)) for model in models)
    if not state_finite:
        raise RuntimeError("non-finite state_dict in API case")
    write_json(root / "runtime.json", runtimes)
    write_json(root / "gpu_pid.json", gpu_process_snapshot())
    return {
        "status": CoverageStatus.EXECUTED.value,
        "prediction_rows": len(prediction_before),
        "model_count": len(models),
        "state_dict_finite": state_finite,
    }


def run_api_coverage(
    project_root: Path,
    config: CampaignConfig,
    run_root: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    if run_root.exists() and not resume:
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=resume)
    cases = api_case_plan()
    pd.DataFrame([asdict(case) for case in cases]).to_parquet(
        run_root / "API_ARGUMENT_COVERAGE_PLAN.parquet",
        index=False,
    )
    results: list[dict[str, Any]] = []
    for case in cases:
        write_json(
            run_root / "progress.json",
            {
                "stage": "api-coverage",
                "completed": len(results),
                "failed": sum(row["status"] == CoverageStatus.FAILED.value for row in results),
                "total": len(cases),
                "current": case.case_id,
            },
        )
        case_root = run_root / "cases" / case.case_id
        result_path = case_root / "result.json"
        if resume and result_path.is_file():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        if case_root.exists():
            shutil.rmtree(case_root)
        case_root.mkdir(parents=True, exist_ok=False)
        started = datetime.now(UTC).isoformat()
        try:
            artifacts = _fit_case(case, config, case_root)
            status = str(artifacts.pop("status"))
            result = ApiCaseResult(
                case=case,
                status=status,
                started_at=started,
                finished_at=datetime.now(UTC).isoformat(),
                artifacts=artifacts,
            )
        except Exception as exc:
            result = ApiCaseResult(
                case=case,
                status=CoverageStatus.FAILED.value,
                started_at=started,
                finished_at=datetime.now(UTC).isoformat(),
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
        payload = result.as_dict()
        write_json(result_path, payload)
        write_sha256s(case_root)
        results.append(payload)

    frame = pd.json_normalize(results)
    frame.to_parquet(run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet", index=False)
    frame.to_csv(run_root / "API_ARGUMENT_COVERAGE_RESULT.csv", index=False)
    failed = int(frame["status"].eq(CoverageStatus.FAILED.value).sum())
    not_applicable = int(frame["status"].eq(CoverageStatus.NOT_APPLICABLE.value).sum())
    from .runner import _code_sha256, _git_snapshot

    manifest = {
        "schema_version": "all-auto-api-coverage-v1",
        "status": "PASS" if failed == 0 else "PARTIAL",
        "api_coverage_status": (
            "PARTIAL_API_COVERAGE" if not_applicable else "COMPLETE_API_COVERAGE"
        ),
        "case_count": len(cases),
        "failed_cases": failed,
        "not_applicable_cases": not_applicable,
        "created_at": datetime.now(UTC).isoformat(),
        "project_root": str(project_root),
        "run_id": run_root.name,
        "git": _git_snapshot(project_root),
        "code_sha256": _code_sha256(project_root),
        "data_sha256": sha256_file(config.data_path.resolve()),
        "neuralforecast_version": __import__("neuralforecast").__version__,
    }
    write_json(
        run_root / "failures.json",
        [row for row in results if row["status"] == CoverageStatus.FAILED.value],
    )
    write_json(run_root / "manifest.json", manifest)
    write_sha256s(run_root)
    return manifest
