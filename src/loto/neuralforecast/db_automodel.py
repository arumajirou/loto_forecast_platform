"""Run NeuralForecast AutoModels against a database table.

The service intentionally separates data extraction, panel normalization, model
planning, and execution.  This keeps database access auditable and allows a dry
run to validate all 36 registered AutoModels without importing PyTorch/Ray.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd

from loto.data.lineage import atomic_write_json, frame_fingerprint, utc_now_iso
from loto.data.lotteries import get_lottery_spec
from loto.models.catalog import ModelSpec, list_model_specs
from loto.models.neuralforecast_adapter import (
    AutoModelRequest,
    construct_auto_model,
    resolve_auto_model_plan,
)
from loto.neuralforecast.runtime_certification import certify_saved_runtime

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LAYOUTS = {"auto", "wide", "long"}


@dataclass(frozen=True)
class DatabaseTableSource:
    """A constrained database table source.

    Arbitrary SQL is deliberately not accepted.  Table, schema and ordering
    identifiers are validated before use.
    """

    db_url: str
    table: str = "normalized_draws"
    schema: str | None = None
    order_by: str | None = "draw_no"


@dataclass(frozen=True)
class AutoModelCampaignConfig:
    source: DatabaseTableSource
    output_dir: str
    game: str = "numbers4"
    layout: Literal["auto", "wide", "long"] = "auto"
    value_columns: tuple[str, ...] = ()
    id_col: str = "unique_id"
    time_col: str = "draw_no"
    target_col: str = "y"
    models: tuple[str, ...] = ("all",)
    exclude_models: tuple[str, ...] = ()
    h: int = 1
    freq: str | int = 1
    val_size: int = 20
    backend: Literal["optuna", "ray"] = "optuna"
    num_samples: int = 10
    time_budget: int | None = None
    cpus: int = 4
    gpus: int = 0
    parallel_trials: int = 1
    workers: int = 1
    max_gpu_jobs: int = 1
    precision: str = "32-true"
    random_seed: int = 1
    search_strategy: Literal["auto", "random", "tpe", "cmaes"] = "auto"
    refit_with_val: bool = False
    local_scaler_type: str | None = None
    local_static_scaler_type: str | None = None
    use_init_models: bool = False
    fit_verbose: bool = False
    save_models: bool = False
    verify_load_predict: bool = True
    require_gpu_execution: bool | None = None
    dry_run: bool = False
    model_configs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.layout not in _LAYOUTS:
            raise ValueError(f"unsupported layout={self.layout!r}")
        if self.h < 1:
            raise ValueError("h must be >= 1")
        if self.val_size < 0:
            raise ValueError("val_size must be >= 0")
        if self.num_samples < 1:
            raise ValueError("num_samples must be >= 1")
        if self.time_budget is not None and self.time_budget < 1:
            raise ValueError("time_budget must be >= 1 when provided")
        if self.parallel_trials < 1:
            raise ValueError("parallel_trials must be >= 1")
        if self.cpus < 1:
            raise ValueError("cpus must be >= 1")
        if self.gpus < 0:
            raise ValueError("gpus must be >= 0")
        if self.workers < 1:
            raise ValueError("workers must be >= 1")
        if self.max_gpu_jobs < 1:
            raise ValueError("max_gpu_jobs must be >= 1")
        if self.gpus > 0 and self.parallel_trials > 1:
            raise ValueError(
                "GPU campaigns require parallel_trials=1; use workers/max_gpu_jobs "
                "for bounded outer concurrency"
            )
        if self.require_gpu_execution is True and self.gpus < 1:
            raise ValueError("require_gpu_execution=True requires gpus >= 1")


def _validate_identifier(value: str, *, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {label} identifier: {value!r}")
    return value


def _sqlite_path(db_url: str) -> Path | None:
    if db_url.startswith("sqlite:///"):
        return Path(db_url.removeprefix("sqlite:///"))
    candidate = Path(db_url).expanduser()
    if "://" not in db_url and candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return candidate
    return None


def mask_database_url(db_url: str) -> str:
    """Mask credentials before writing manifests or logs."""
    if "://" not in db_url:
        return str(Path(db_url).expanduser())
    parts = urlsplit(db_url)
    if parts.username is None:
        return db_url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    user = parts.username
    netloc = f"{user}:***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def load_database_table(source: DatabaseTableSource) -> pd.DataFrame:
    """Load one complete table from SQLite or a SQLAlchemy-supported database."""
    table = _validate_identifier(source.table, label="table")
    schema = _validate_identifier(source.schema, label="schema") if source.schema else None
    order_by = _validate_identifier(source.order_by, label="order_by") if source.order_by else None
    sqlite_path = _sqlite_path(source.db_url)
    if sqlite_path is not None:
        if not sqlite_path.exists():
            raise FileNotFoundError(sqlite_path)
        query = f'SELECT * FROM "{table}"'
        if order_by:
            query += f' ORDER BY "{order_by}"'
        with sqlite3.connect(sqlite_path) as connection:
            return pd.read_sql_query(query, connection)

    try:
        from sqlalchemy import create_engine
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("non-SQLite databases require the full/postgres extra") from exc

    engine = create_engine(source.db_url, pool_pre_ping=True)
    try:
        frame = pd.read_sql_table(table, engine, schema=schema)
    finally:
        engine.dispose()
    if order_by:
        if order_by not in frame.columns:
            raise ValueError(f"order_by column {order_by!r} is absent from {table!r}")
        frame = frame.sort_values(order_by, kind="stable")
    return frame.reset_index(drop=True)


def _default_value_columns(game: str) -> tuple[str, ...]:
    spec = get_lottery_spec(game)
    if spec.kind == "numbers":
        return tuple(f"d{i}" for i in range(1, int(spec.digits_count or 0) + 1))
    return tuple(f"n{i}" for i in range(1, int(spec.main_count or 0) + 1))


def prepare_panel(
    frame: pd.DataFrame,
    *,
    game: str,
    layout: Literal["auto", "wide", "long"] = "auto",
    value_columns: tuple[str, ...] = (),
    id_col: str = "unique_id",
    time_col: str = "draw_no",
    target_col: str = "y",
) -> pd.DataFrame:
    """Normalize a database table to NeuralForecast's ``unique_id/ds/y`` panel."""
    if layout not in _LAYOUTS:
        raise ValueError(f"unsupported layout={layout!r}")
    spec = get_lottery_spec(game)
    requested_values = tuple(value_columns) or _default_value_columns(game)
    resolved_layout = layout
    if resolved_layout == "auto":
        has_long = {id_col, time_col, target_col}.issubset(frame.columns)
        has_wide = bool(requested_values) and set(requested_values).issubset(frame.columns)
        if has_long:
            resolved_layout = "long"
        elif has_wide:
            resolved_layout = "wide"
        else:
            raise ValueError(
                "could not infer table layout; expected long columns "
                f"{[id_col, time_col, target_col]} or wide columns {list(requested_values)}"
            )

    if resolved_layout == "long":
        required = {id_col, time_col, target_col}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"long table is missing columns: {missing}")
        panel = frame[[id_col, time_col, target_col]].rename(
            columns={id_col: "unique_id", time_col: "ds", target_col: "y"}
        )
    else:
        if time_col not in frame.columns:
            raise ValueError(f"wide table is missing time column {time_col!r}")
        missing = [column for column in requested_values if column not in frame.columns]
        if missing:
            raise ValueError(f"wide table is missing value columns: {missing}")
        panel = frame[[time_col, *requested_values]].melt(
            id_vars=[time_col],
            value_vars=list(requested_values),
            var_name="_position",
            value_name="y",
        )
        ordinal = {column: index for index, column in enumerate(requested_values, start=1)}
        panel["unique_id"] = panel["_position"].map(
            lambda value: f"{game}-p{ordinal[str(value)]:02d}-{value}"
        )
        panel = panel.rename(columns={time_col: "ds"})[["unique_id", "ds", "y"]]

    panel = panel.copy()
    panel["unique_id"] = panel["unique_id"].astype(str)
    panel["y"] = pd.to_numeric(panel["y"], errors="coerce")
    if panel["y"].isna().any():
        bad = int(panel["y"].isna().sum())
        raise ValueError(f"target contains {bad} missing/non-numeric values")
    if panel[["unique_id", "ds"]].duplicated().any():
        raise ValueError("duplicate (unique_id, ds) rows detected")
    if spec.kind == "numbers":
        out_of_range = (panel["y"] < spec.number_min) | (panel["y"] > spec.number_max)
        if out_of_range.any():
            raise ValueError(
                f"{int(out_of_range.sum())} targets fall outside "
                f"[{spec.number_min}, {spec.number_max}]"
            )
    panel = panel.sort_values(["unique_id", "ds"], kind="stable").reset_index(drop=True)
    counts = panel.groupby("unique_id", sort=False)["ds"].size()
    if counts.nunique() != 1:
        raise ValueError(f"all series must have equal length; lengths={counts.to_dict()}")
    return panel


def list_automodel_specs() -> list[ModelSpec]:
    return [spec for spec in list_model_specs() if spec.library == "neuralforecast_auto"]


def _resolve_specs(requested: tuple[str, ...], excluded: tuple[str, ...]) -> list[ModelSpec]:
    all_specs = list_automodel_specs()
    by_token = {token: spec for spec in all_specs for token in (spec.model_id, spec.class_name)}
    if not requested or "all" in requested:
        selected = list(all_specs)
    else:
        unknown = sorted(token for token in requested if token not in by_token)
        if unknown:
            raise ValueError(f"unknown NeuralForecast AutoModels: {unknown}")
        selected = [by_token[token] for token in requested]
    excluded_specs = {by_token[token].model_id for token in excluded if token in by_token}
    unknown_excluded = sorted(token for token in excluded if token not in by_token)
    if unknown_excluded:
        raise ValueError(f"unknown excluded AutoModels: {unknown_excluded}")
    deduplicated: dict[str, ModelSpec] = {}
    for spec in selected:
        if spec.model_id not in excluded_specs:
            deduplicated[spec.model_id] = spec
    if not deduplicated:
        raise ValueError("no AutoModels remain after filtering")
    return list(deduplicated.values())


def _build_hint_panel(panel: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, dict[str, str]]:
    bottom_ids = sorted(panel["unique_id"].unique().tolist())
    pivot = panel.pivot(index="ds", columns="unique_id", values="y").sort_index()
    pivot = pivot[bottom_ids]
    top_id = "00-total"
    hint_ids = {source: f"{index:02d}-{source}" for index, source in enumerate(bottom_ids, 1)}
    rows = [
        pd.DataFrame({"unique_id": top_id, "ds": pivot.index, "y": pivot.sum(axis=1).to_numpy()})
    ]
    for source in bottom_ids:
        rows.append(
            pd.DataFrame(
                {
                    "unique_id": hint_ids[source],
                    "ds": pivot.index,
                    "y": pivot[source].to_numpy(),
                }
            )
        )
    hint_panel = pd.concat(rows, ignore_index=True).sort_values(["unique_id", "ds"])
    summing = np.vstack([np.ones((1, len(bottom_ids))), np.eye(len(bottom_ids))])
    reverse = {value: key for key, value in hint_ids.items()}
    return hint_panel.reset_index(drop=True), summing, reverse


def _construct_auto_hint(config: AutoModelCampaignConfig, panel: pd.DataFrame):
    try:
        from neuralforecast.auto import AutoHINT, RayOptions
        from neuralforecast.losses.pytorch import DistributionLoss, MQLoss
        from neuralforecast.models import NHITS
        from ray import tune
    except ImportError as exc:
        raise RuntimeError("AutoHINT requires neuralforecast and ray[tune]") from exc

    hint_panel, summing, reverse_ids = _build_hint_panel(panel)
    input_size = max(config.h * 4, min(64, hint_panel.groupby("unique_id").size().min() // 2))
    max_steps = int(config.model_configs.get("nf-auto-hint", {}).get("max_steps", 200))
    hint_config = {
        "input_size": tune.choice([input_size]),
        "max_steps": tune.choice([max_steps]),
        "val_check_steps": tune.choice([max(1, min(50, max_steps))]),
        "learning_rate": tune.choice([1e-3]),
        "batch_size": tune.choice([max(8, len(reverse_ids) + 1)]),
        "windows_batch_size": tune.choice([128]),
        "n_pool_kernel_size": tune.choice([[1, 1, 1]]),
        "n_freq_downsample": tune.choice([[1, 1, 1]]),
        "n_blocks": tune.choice([[1, 1, 1]]),
        "mlp_units": tune.choice([[[64, 64], [64, 64], [64, 64]]]),
        "activation": tune.choice(["ReLU"]),
        "interpolation_mode": tune.choice(["linear"]),
        "random_seed": tune.choice([config.random_seed]),
        "reconciliation": tune.choice(["BottomUp", "MinTraceOLS", "MinTraceWLS"]),
    }
    model = AutoHINT(
        cls_model=NHITS,
        h=config.h,
        loss=DistributionLoss(distribution="StudentT", level=[80, 90], return_params=False),
        valid_loss=MQLoss(level=[80, 90]),
        S=summing,
        config=hint_config,
        num_samples=config.num_samples,
        time_budget=config.time_budget,
        refit_with_val=config.refit_with_val,
        ray_options=RayOptions(cpus=config.cpus, gpus=config.gpus),
        verbose=True,
        alias="AutoHINT-ray",
        backend="ray",
    )
    return model, hint_panel, reverse_ids, {"hierarchy_shape": list(summing.shape)}


def _prediction_value_column(prediction: pd.DataFrame, alias: str) -> str:
    ignored = {"unique_id", "ds", "cutoff"}
    candidates = [column for column in prediction.columns if column not in ignored]
    if alias in candidates:
        return alias
    point_candidates = [
        column
        for column in candidates
        if not any(
            marker in str(column).lower() for marker in ("-lo-", "-hi-", "median", "quantile")
        )
    ]
    if point_candidates:
        return str(point_candidates[0])
    if not candidates:
        raise ValueError("NeuralForecast.predict returned no forecast value columns")
    return str(candidates[0])


def _decode_prediction_rows(
    prediction: pd.DataFrame,
    *,
    game: str,
    value_col: str,
    reverse_ids: dict[str, str] | None = None,
) -> pd.DataFrame:
    spec = get_lottery_spec(game)
    decoded = prediction.copy()
    if reverse_ids:
        decoded = decoded[decoded["unique_id"].isin(reverse_ids)].copy()
        decoded["unique_id"] = decoded["unique_id"].map(reverse_ids)
    decoded["raw_prediction"] = pd.to_numeric(decoded[value_col], errors="coerce")
    if decoded["raw_prediction"].isna().any():
        raise ValueError("forecast contains non-numeric point predictions")
    decoded["decoded_prediction"] = decoded["raw_prediction"].round()
    decoded["decoded_prediction"] = decoded["decoded_prediction"].clip(
        lower=spec.number_min, upper=spec.number_max
    )
    if spec.kind == "numbers":
        decoded["decoded_prediction"] = decoded["decoded_prediction"].astype(int)
    return decoded.sort_values(["ds", "unique_id"], kind="stable").reset_index(drop=True)


def _single_model_config(config: AutoModelCampaignConfig, spec: ModelSpec) -> dict[str, Any]:
    selected = config.model_configs.get(spec.model_id) or config.model_configs.get(spec.class_name)
    return dict(selected or {})


def _run_single_model(
    config: AutoModelCampaignConfig,
    spec: ModelSpec,
    panel: pd.DataFrame,
) -> dict[str, Any]:
    started = time.perf_counter()
    model_dir = Path(config.output_dir) / "models" / spec.model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "model_id": spec.model_id,
        "class_name": spec.class_name,
        "status": "RUNNING",
        "certification_status": "PENDING",
        "started_at": utc_now_iso(),
    }
    try:
        from neuralforecast import NeuralForecast

        reverse_ids: dict[str, str] | None = None
        metadata: dict[str, Any] = {}
        fit_panel = panel
        if spec.class_name == "AutoHINT":
            model, fit_panel, reverse_ids, metadata = _construct_auto_hint(config, panel)
            alias = "AutoHINT-ray"
            plan_payload = {
                "special_constructor": "AutoHINT+NHITS",
                "backend": "ray",
                "backend_override": config.backend != "ray",
                **metadata,
            }
        else:
            request = AutoModelRequest(
                model_name=spec.class_name,
                h=config.h,
                config=_single_model_config(config, spec),
                backend=config.backend,
                cpus=config.cpus,
                gpus=config.gpus,
                parallel_trials=config.parallel_trials,
                num_samples=config.num_samples,
                time_budget=config.time_budget,
                refit_with_val=config.refit_with_val,
                precision=config.precision,
                n_series=int(panel["unique_id"].nunique()),
                random_seed=config.random_seed,
                search_strategy=config.search_strategy,
                verbose=True,
            )
            plan = resolve_auto_model_plan(request)
            model = construct_auto_model(plan)
            alias = str(plan.constructor_kwargs.get("alias", spec.class_name))
            plan_payload = {
                "backend": plan.backend,
                "config": plan.config,
                "precision": plan.precision,
                "adjustments": list(plan.adjustments),
                "search_algorithm": plan.search_algorithm,
                "constructor_keys": sorted(plan.constructor_kwargs),
            }

        nf = NeuralForecast(
            models=[model],
            freq=config.freq,
            local_scaler_type=config.local_scaler_type,
            local_static_scaler_type=config.local_static_scaler_type,
        )
        nf.fit(
            df=fit_panel,
            val_size=config.val_size,
            use_init_models=config.use_init_models,
            verbose=config.fit_verbose,
            id_col="unique_id",
            time_col="ds",
            target_col="y",
        )
        prediction = nf.predict(verbose=config.fit_verbose)
        value_col = _prediction_value_column(prediction, alias)
        decoded = _decode_prediction_rows(
            prediction,
            game=config.game,
            value_col=value_col,
            reverse_ids=reverse_ids,
        )
        prediction_path = model_dir / "predictions.csv"
        decoded.to_csv(prediction_path, index=False)

        certification: dict[str, Any] = {
            "status": "SKIPPED",
            "reason": "verify_load_predict is disabled",
        }
        certification_status = "TRAIN_ONLY"
        model_path = model_dir / "neuralforecast"
        if config.verify_load_predict:
            require_gpu = (
                config.gpus > 0
                if config.require_gpu_execution is None
                else config.require_gpu_execution
            )
            certification = certify_saved_runtime(
                neuralforecast=nf,
                neuralforecast_class=NeuralForecast,
                model_path=model_path,
                prediction_before=prediction,
                alias=alias,
                verbose=config.fit_verbose,
                require_gpu=require_gpu,
            )
            atomic_write_json(model_dir / "runtime_certification.json", certification)
            certification_status = "RUNTIME_CERTIFIED"
            if not config.save_models:
                shutil.rmtree(model_path, ignore_errors=True)
        elif config.save_models:
            nf.save(str(model_path), save_dataset=True, overwrite=True)

        report.update(
            {
                "status": "SUCCEEDED",
                "certification_status": certification_status,
                "finished_at": utc_now_iso(),
                "elapsed_seconds": time.perf_counter() - started,
                "prediction_rows": int(len(decoded)),
                "point_column": value_col,
                "prediction_path": str(prediction_path),
                "plan": plan_payload,
                "runtime_certification": certification,
                "decoded_predictions": decoded[
                    ["unique_id", "ds", "raw_prediction", "decoded_prediction"]
                ].to_dict(orient="records"),
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "FAILED",
                "certification_status": "FAILED",
                "finished_at": utc_now_iso(),
                "elapsed_seconds": time.perf_counter() - started,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    atomic_write_json(model_dir / "run_report.json", report)
    return report


def _worker_entry(config_payload: dict[str, Any], spec_payload: dict[str, Any], panel_path: str):
    source_payload = config_payload.pop("source")
    config = AutoModelCampaignConfig(
        source=DatabaseTableSource(**source_payload),
        **config_payload,
    )
    spec = next(
        item for item in list_automodel_specs() if item.model_id == spec_payload["model_id"]
    )
    panel = pd.read_csv(panel_path)
    return _run_single_model(config, spec, panel)


def build_campaign_plan(config: AutoModelCampaignConfig, panel: pd.DataFrame) -> dict[str, Any]:
    specs = _resolve_specs(config.models, config.exclude_models)
    effective_workers = config.workers
    queue_policy = "cpu_parallel"
    if config.gpus > 0:
        effective_workers = min(config.workers, config.max_gpu_jobs)
        queue_policy = "gpu_bounded_queue"
    require_gpu = (
        config.gpus > 0 if config.require_gpu_execution is None else config.require_gpu_execution
    )
    return {
        "schema_version": "1.1.0",
        "game": config.game,
        "source": {
            "db_url": mask_database_url(config.source.db_url),
            "table": config.source.table,
            "schema": config.source.schema,
            "order_by": config.source.order_by,
        },
        "panel": {
            "rows": int(len(panel)),
            "series": int(panel["unique_id"].nunique()),
            "observations_per_series": int(panel.groupby("unique_id").size().iloc[0]),
            "sha256": frame_fingerprint(panel),
            "columns": list(panel.columns),
        },
        "core": {
            "freq": config.freq,
            "local_scaler_type": config.local_scaler_type,
            "local_static_scaler_type": config.local_static_scaler_type,
        },
        "fit": {
            "val_size": config.val_size,
            "use_init_models": config.use_init_models,
            "verbose": config.fit_verbose,
            "id_col": "unique_id",
            "time_col": "ds",
            "target_col": "y",
        },
        "optimization": {
            "backend": config.backend,
            "num_samples": config.num_samples,
            "time_budget": config.time_budget,
            "cpus_per_model": config.cpus,
            "gpus_per_model": config.gpus,
            "requested_workers": config.workers,
            "effective_workers": effective_workers,
            "max_gpu_jobs": config.max_gpu_jobs,
            "parallel_trials": config.parallel_trials,
            "queue_policy": queue_policy,
            "maximum_parallel_trials": effective_workers * config.parallel_trials,
            "gpu_parallel_trials_fail_closed": config.gpus > 0,
        },
        "runtime_certification": {
            "verify_load_predict": config.verify_load_predict,
            "require_gpu_execution": require_gpu,
            "retain_model_bundle": config.save_models,
            "required_checks": [
                "save",
                "load",
                "predict",
                "finite_predictions",
                "finite_state_dict",
                "shape_match",
                "prediction_match",
                "device_evidence",
                "cpu_fallback_rejection_when_gpu_required",
            ],
        },
        "models": [
            {
                "model_id": spec.model_id,
                "class_name": spec.class_name,
                "special_handling": "hierarchical-ray-backend-override"
                if spec.class_name == "AutoHINT"
                else None,
                "requires_n_series": spec.class_name
                in {
                    "AutoTSMixer",
                    "AutoTSMixerx",
                    "AutoTimeMixer",
                    "AutoRMoK",
                    "AutoSOFTS",
                    "AutoSOFTSSharp",
                    "AutoXLinear",
                    "AutoStemGNN",
                    "AutoMLPMultivariate",
                    "AutoiTransformer",
                    "AutoTimeXer",
                },
            }
            for spec in specs
        ],
    }


def run_automodel_campaign(config: AutoModelCampaignConfig) -> dict[str, Any]:
    """Load the table, normalize it and execute the selected AutoModels."""
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = load_database_table(config.source)
    panel = prepare_panel(
        frame,
        game=config.game,
        layout=config.layout,
        value_columns=config.value_columns,
        id_col=config.id_col,
        time_col=config.time_col,
        target_col=config.target_col,
    )
    observations_per_series = int(panel.groupby("unique_id", sort=False).size().iloc[0])
    if config.val_size and config.val_size < config.h:
        raise ValueError("val_size must be 0 or >= h")
    if config.val_size >= observations_per_series:
        raise ValueError(
            "val_size must be smaller than observations per series; "
            f"val_size={config.val_size}, observations={observations_per_series}"
        )
    panel_path = output / "input_panel.csv"
    panel.to_csv(panel_path, index=False)
    plan = build_campaign_plan(config, panel)
    plan_path = atomic_write_json(output / "campaign_plan.json", plan)
    if config.dry_run:
        result = {
            "schema_version": "1.1.0",
            "status": "DRY_RUN_VERIFIED",
            "certification_status": "NOT_EXECUTED",
            "plan_path": str(plan_path),
            "panel_path": str(panel_path),
            "model_count": len(plan["models"]),
            "plan": plan,
        }
        atomic_write_json(output / "campaign_report.json", result)
        return result

    specs = _resolve_specs(config.models, config.exclude_models)
    effective_workers = int(plan["optimization"]["effective_workers"])
    reports: list[dict[str, Any]] = []
    if effective_workers == 1:
        for spec in specs:
            reports.append(_run_single_model(config, spec, panel))
    else:
        payload = asdict(config)
        with ProcessPoolExecutor(max_workers=effective_workers) as executor:
            futures = {
                executor.submit(
                    _worker_entry,
                    json.loads(json.dumps(payload, default=str)),
                    {"model_id": spec.model_id},
                    str(panel_path),
                ): spec.model_id
                for spec in specs
            }
            for future in as_completed(futures):
                try:
                    reports.append(future.result())
                except Exception as exc:  # process bootstrap failure
                    reports.append(
                        {
                            "model_id": futures[future],
                            "status": "FAILED",
                            "certification_status": "FAILED",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    succeeded = [report for report in reports if report.get("status") == "SUCCEEDED"]
    failed = [report for report in reports if report.get("status") != "SUCCEEDED"]
    certified = [
        report
        for report in succeeded
        if report.get("certification_status") == "RUNTIME_CERTIFIED"
    ]
    status = "SUCCEEDED" if not failed else "PARTIAL" if succeeded else "FAILED"
    if failed:
        certification_status = "PARTIAL" if certified else "FAILED"
    elif len(certified) == len(reports):
        certification_status = "RUNTIME_CERTIFIED"
    else:
        certification_status = "TRAIN_ONLY"
    result = {
        "schema_version": "1.1.0",
        "status": status,
        "certification_status": certification_status,
        "started_model_count": len(reports),
        "succeeded_model_count": len(succeeded),
        "runtime_certified_model_count": len(certified),
        "failed_model_count": len(failed),
        "plan_path": str(plan_path),
        "panel_path": str(panel_path),
        "reports": sorted(reports, key=lambda row: str(row.get("model_id"))),
    }
    atomic_write_json(output / "campaign_report.json", result)
    return result
