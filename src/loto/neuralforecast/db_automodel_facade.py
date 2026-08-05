"""Install failure-durable search-space evidence on the database campaign."""

from __future__ import annotations

import json
import traceback
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any, Callable

import pandas as pd

from loto.models.neuralforecast_search_space import (
    SearchSpaceProfile,
    profile_ray_config,
)
from loto.neuralforecast.db_search_space_persistence import (
    persist_database_search_space_evidence,
    runtime_profile_for_model,
    summarize_database_search_space_reports,
    unavailable_autohint_profile,
)


@dataclass
class _ExecutionContext:
    config: Any
    spec: Any
    model_dir: Path
    resolve_delegate: Callable[[Any], Any]
    construct_delegate: Callable[[Any], Any]
    evidence: dict[str, Any] | None = None
    planning_profile: SearchSpaceProfile | None = None


_CONTEXT: ContextVar[_ExecutionContext | None] = ContextVar(
    "db_search_space_execution_context", default=None
)
_INTERCEPT_LOCK = RLock()
_CORE: ModuleType | None = None
_ORIGINALS: dict[str, Any] = {}


def _persist(
    context: _ExecutionContext,
    profile: SearchSpaceProfile,
    *,
    phase: str,
    backend: str,
    planning_profile_sha256: str | None = None,
) -> dict[str, Any]:
    evidence = persist_database_search_space_evidence(
        context.model_dir,
        profile,
        phase=phase,
        model_id=context.spec.model_id,
        class_name=context.spec.class_name,
        backend=backend,
        search_seed=context.config.random_seed,
        num_samples=context.config.num_samples,
        planning_profile_sha256=planning_profile_sha256,
    )
    context.evidence = evidence
    if phase == "planning":
        context.planning_profile = profile
    return evidence


def _resolve_interceptor(request: Any) -> Any:
    context = _CONTEXT.get()
    if context is None:
        raise RuntimeError("search-space resolve interceptor has no execution context")
    plan = context.resolve_delegate(request)
    profile = plan.search_space_profile
    if profile is None:
        from loto.models.neuralforecast_search_space import (
            unavailable_search_space_profile,
        )

        profile = unavailable_search_space_profile(
            backend=plan.backend,
            model_name=plan.model_name,
            reason="dependency-light plan did not expose a search-space profile",
        )
    _persist(context, profile, phase="planning", backend=plan.backend)
    return plan


def _construct_interceptor(plan: Any) -> Any:
    context = _CONTEXT.get()
    if context is None:
        raise RuntimeError("search-space construct interceptor has no execution context")
    model = context.construct_delegate(plan)
    fallback = context.planning_profile or plan.search_space_profile
    if fallback is None:
        raise RuntimeError("planning search-space profile is unavailable")
    runtime_profile = runtime_profile_for_model(
        model,
        backend=plan.backend,
        model_name=plan.model_name,
        fallback=fallback,
    )
    _persist(
        context,
        runtime_profile,
        phase="runtime_resolved",
        backend=plan.backend,
        planning_profile_sha256=fallback.profile_sha256,
    )
    return model


def _construct_auto_hint(config: Any, panel: pd.DataFrame):
    if _CORE is None:
        raise RuntimeError("database AutoModel persistence installer is unavailable")
    try:
        from neuralforecast.auto import AutoHINT, RayOptions
        from neuralforecast.losses.pytorch import DistributionLoss, MQLoss
        from neuralforecast.models import NHITS
        from ray import tune
    except ImportError as exc:
        raise RuntimeError("AutoHINT requires neuralforecast and ray[tune]") from exc

    hint_panel, summing, reverse_ids = _CORE._build_hint_panel(panel)
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
    context = _CONTEXT.get()
    if context is not None:
        runtime_profile = profile_ray_config(hint_config, model_name="AutoHINT")
        fallback = context.planning_profile
        _persist(
            context,
            runtime_profile,
            phase="runtime_resolved",
            backend="ray",
            planning_profile_sha256=(
                fallback.profile_sha256 if fallback is not None else None
            ),
        )
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


def _run_single_model(config: Any, spec: Any, panel: pd.DataFrame) -> dict[str, Any]:
    if _CORE is None:
        raise RuntimeError("database AutoModel persistence installer is unavailable")
    model_dir = Path(config.output_dir) / "models" / spec.model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    with _INTERCEPT_LOCK:
        resolve_delegate = _CORE.resolve_auto_model_plan
        construct_delegate = _CORE.construct_auto_model
        if resolve_delegate is _resolve_interceptor:
            resolve_delegate = _ORIGINALS["resolve_auto_model_plan"]
        if construct_delegate is _construct_interceptor:
            construct_delegate = _ORIGINALS["construct_auto_model"]
        context = _ExecutionContext(
            config=config,
            spec=spec,
            model_dir=model_dir,
            resolve_delegate=resolve_delegate,
            construct_delegate=construct_delegate,
        )
        token = _CONTEXT.set(context)
        _CORE.resolve_auto_model_plan = _resolve_interceptor
        _CORE.construct_auto_model = _construct_interceptor
        try:
            if spec.class_name == "AutoHINT":
                _persist(
                    context,
                    unavailable_autohint_profile(),
                    phase="planning",
                    backend="ray",
                )
            report = _ORIGINALS["run_single_model"](config, spec, panel)
        except Exception as exc:  # defensive boundary outside the stable core
            report = {
                "model_id": spec.model_id,
                "class_name": spec.class_name,
                "status": "FAILED",
                "certification_status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        finally:
            _CORE.resolve_auto_model_plan = resolve_delegate
            _CORE.construct_auto_model = construct_delegate
            _CONTEXT.reset(token)
    if context.evidence is not None:
        report["search_space_evidence"] = context.evidence
    else:
        report.setdefault("search_space_evidence", {"status": "MISSING"})
    _CORE.atomic_write_json(model_dir / "run_report.json", report)
    return report


def _worker_entry(
    config_payload: dict[str, Any], spec_payload: dict[str, Any], panel_path: str
) -> dict[str, Any]:
    from loto.neuralforecast import db_automodel as db

    source_payload = config_payload.pop("source")
    config = db.AutoModelCampaignConfig(
        source=db.DatabaseTableSource(**source_payload),
        **config_payload,
    )
    spec = next(
        item for item in db.list_automodel_specs() if item.model_id == spec_payload["model_id"]
    )
    return db._run_single_model(config, spec, pd.read_csv(panel_path))


def build_campaign_plan(config: Any, panel: pd.DataFrame) -> dict[str, Any]:
    plan = _ORIGINALS["build_campaign_plan"](config, panel)
    plan["search_space_artifacts"] = {
        "persistence_timing": "before_model_construction",
        "model_directory_files": [
            "SEARCH_SPACE_PROFILE.json",
            "SEARCH_SPACE_PROFILE.sha256",
            "SEARCH_SPACE_PROFILE_MANIFEST.json",
            "SEARCH_SPACE_PROFILE_MANIFEST.sha256",
        ],
        "verification": "read_after_write_fail_closed",
        "campaign_report_aggregation": True,
    }
    return plan


def run_automodel_campaign(config: Any) -> dict[str, Any]:
    result = _ORIGINALS["run_automodel_campaign"](config)
    if config.dry_run:
        return result
    reports = list(result.get("reports", []))
    summary = summarize_database_search_space_reports(reports)
    result.update(
        {
            "search_space_artifact_status": summary["status"],
            "search_space_verified_model_count": summary["verified_model_count"],
            "search_space_artifacts": summary,
        }
    )
    if _CORE is None:
        raise RuntimeError("database AutoModel persistence installer is unavailable")
    _CORE.atomic_write_json(Path(config.output_dir) / "campaign_report.json", result)
    return result


def install(core: ModuleType) -> None:
    """Install once without moving the stable module or changing public classes."""

    global _CORE
    stored = getattr(core, "_db_search_space_persistence_originals", None)
    if getattr(core, "_db_search_space_persistence_installed", False):
        if not isinstance(stored, dict):
            raise RuntimeError("installed database persistence facade lost original functions")
        _CORE = core
        _ORIGINALS.clear()
        _ORIGINALS.update(stored)
        return
    _CORE = core
    originals = {
        "resolve_auto_model_plan": core.resolve_auto_model_plan,
        "construct_auto_model": core.construct_auto_model,
        "construct_auto_hint": core._construct_auto_hint,
        "run_single_model": core._run_single_model,
        "worker_entry": core._worker_entry,
        "build_campaign_plan": core.build_campaign_plan,
        "run_automodel_campaign": core.run_automodel_campaign,
    }
    _ORIGINALS.clear()
    _ORIGINALS.update(originals)
    core._db_search_space_persistence_originals = originals
    core._construct_auto_hint = _construct_auto_hint
    core._run_single_model = _run_single_model
    core._worker_entry = _worker_entry
    core.build_campaign_plan = build_campaign_plan
    core.run_automodel_campaign = run_automodel_campaign
    core._db_search_space_persistence_installed = True
