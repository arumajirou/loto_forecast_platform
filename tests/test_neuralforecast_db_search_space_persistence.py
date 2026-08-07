from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from loto.models.neuralforecast_search_space import profile_fixed_config
from loto.neuralforecast import db_automodel_facade as facade


def _atomic_write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, default=str), encoding="utf-8")
    return target


def _fresh_core(*, run_single=None, run_campaign=None) -> ModuleType:
    core = ModuleType("fake_db_core")
    core.atomic_write_json = _atomic_write_json

    def build_hint_panel(panel):
        return panel, [[1.0]], {}

    def resolve(request):
        return request

    def construct(plan):
        return plan

    def construct_hint(config, panel):
        return object(), panel, None, {}

    def default_run_single(config, spec, panel):
        return {
            "model_id": spec.model_id,
            "class_name": spec.class_name,
            "status": "SUCCEEDED",
            "certification_status": "TRAIN_ONLY",
        }

    def worker_entry(*args):
        return None

    def build_plan(config, panel):
        return {"schema_version": "1.1.0"}

    def default_campaign(config):
        return {"schema_version": "1.1.0", "reports": []}

    def campaign_config(**kwargs):
        return SimpleNamespace(**kwargs)

    def source(**kwargs):
        return SimpleNamespace(**kwargs)

    def specs():
        return []

    core._build_hint_panel = build_hint_panel
    core.resolve_auto_model_plan = resolve
    core.construct_auto_model = construct
    core._construct_auto_hint = construct_hint
    core._run_single_model = run_single or default_run_single
    core._worker_entry = worker_entry
    core.build_campaign_plan = build_plan
    core.run_automodel_campaign = run_campaign or default_campaign
    core.AutoModelCampaignConfig = campaign_config
    core.DatabaseTableSource = source
    core.list_automodel_specs = specs

    facade._CORE = None
    facade._ORIGINALS.clear()
    facade.install(core)
    return core


def _config(tmp_path: Path, *, dry_run: bool = False):
    return SimpleNamespace(
        output_dir=str(tmp_path),
        random_seed=1,
        num_samples=10,
        backend="optuna",
        dry_run=dry_run,
        h=1,
        model_configs={},
        cpus=1,
        gpus=0,
        time_budget=None,
        refit_with_val=False,
    )


def _spec(class_name: str = "AutoDLinear"):
    return SimpleNamespace(model_id="nf-auto-dlinear", class_name=class_name)


def test_facade_persists_planning_and_runtime_profiles_and_restores_hooks(
    tmp_path: Path,
) -> None:
    planning = profile_fixed_config(
        {"input_size": 8}, backend="optuna", model_name="AutoDLinear"
    )
    runtime = profile_fixed_config(
        {"input_size": 16}, backend="optuna", model_name="AutoDLinear"
    )
    plan = SimpleNamespace(
        search_space_profile=planning,
        backend="optuna",
        model_name="AutoDLinear",
    )
    calls = []

    def run_single(config, spec, _panel):
        resolved = core.resolve_auto_model_plan(object())
        model = core.construct_auto_model(resolved)
        calls.append(model)
        return {
            "model_id": spec.model_id,
            "class_name": spec.class_name,
            "status": "SUCCEEDED",
            "certification_status": "TRAIN_ONLY",
        }

    core = _fresh_core(run_single=run_single)

    def monkey_resolve(_request):
        return plan

    def monkey_construct(_plan):
        return SimpleNamespace(search_space_profile=runtime.model_dump(mode="json"))

    core.resolve_auto_model_plan = monkey_resolve
    core.construct_auto_model = monkey_construct

    report = core._run_single_model(_config(tmp_path), _spec(), pd.DataFrame())

    assert calls
    assert core.resolve_auto_model_plan is monkey_resolve
    assert core.construct_auto_model is monkey_construct
    evidence = report["search_space_evidence"]
    assert evidence["phase"] == "runtime_resolved"
    assert evidence["profile"]["profile_sha256"] == runtime.profile_sha256
    assert evidence["artifacts"]["verification_status"] == "PASS"
    model_dir = tmp_path / "models" / "nf-auto-dlinear"
    manifest = json.loads(
        (model_dir / "SEARCH_SPACE_PROFILE_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["context"]["planning_profile_sha256"] == planning.profile_sha256
    persisted = json.loads((model_dir / "run_report.json").read_text(encoding="utf-8"))
    assert persisted["search_space_evidence"]["phase"] == "runtime_resolved"


def test_constructor_failure_keeps_planning_evidence_and_restores_hooks(
    tmp_path: Path,
) -> None:
    planning = profile_fixed_config(
        {"input_size": 8}, backend="optuna", model_name="AutoDLinear"
    )
    plan = SimpleNamespace(
        search_space_profile=planning,
        backend="optuna",
        model_name="AutoDLinear",
    )

    def run_single(config, spec, _panel):
        resolved = core.resolve_auto_model_plan(object())
        core.construct_auto_model(resolved)
        raise AssertionError("unreachable")

    core = _fresh_core(run_single=run_single)

    def monkey_resolve(_request):
        return plan

    def monkey_construct(_plan):
        raise RuntimeError("constructor intentionally failed")

    core.resolve_auto_model_plan = monkey_resolve
    core.construct_auto_model = monkey_construct

    report = core._run_single_model(_config(tmp_path), _spec(), pd.DataFrame())

    assert report["status"] == "FAILED"
    assert "constructor intentionally failed" in report["error"]
    assert report["search_space_evidence"]["phase"] == "planning"
    assert report["search_space_evidence"]["artifacts"]["verification_status"] == "PASS"
    assert core.resolve_auto_model_plan is monkey_resolve
    assert core.construct_auto_model is monkey_construct


def test_plan_resolution_failure_keeps_preflight_evidence(tmp_path: Path) -> None:
    def run_single(config, spec, panel):
        core.resolve_auto_model_plan(object())
        raise AssertionError("unreachable")

    core = _fresh_core(run_single=run_single)

    def fail_resolve(_request):
        raise ValueError("plan intentionally failed")

    core.resolve_auto_model_plan = fail_resolve
    report = core._run_single_model(_config(tmp_path), _spec(), pd.DataFrame())

    assert report["status"] == "FAILED"
    assert "plan intentionally failed" in report["error"]
    evidence = report["search_space_evidence"]
    assert evidence["phase"] == "planning"
    assert evidence["profile"]["completeness"] == "UNAVAILABLE"
    assert evidence["artifacts"]["verification_status"] == "PASS"


def test_autohint_persists_unavailable_then_ray_profile_before_constructor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Choice:
        def __init__(self, categories):
            self.categories = tuple(categories)

    constructor_observation = {}

    class FakeAutoHINT:
        def __init__(self, **_kwargs):
            path = tmp_path / "models" / "nf-auto-dlinear" / "SEARCH_SPACE_PROFILE.json"
            constructor_observation.update(json.loads(path.read_text(encoding="utf-8")))

    class FakeRayOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeLoss:
        def __init__(self, **_kwargs):
            pass

    auto_module = ModuleType("neuralforecast.auto")
    auto_module.AutoHINT = FakeAutoHINT
    auto_module.RayOptions = FakeRayOptions
    losses_module = ModuleType("neuralforecast.losses.pytorch")
    losses_module.DistributionLoss = FakeLoss
    losses_module.MQLoss = FakeLoss
    models_module = ModuleType("neuralforecast.models")
    models_module.NHITS = object
    ray_module = ModuleType("ray")
    ray_module.tune = SimpleNamespace(choice=lambda values: Choice(values))
    monkeypatch.setitem(sys.modules, "neuralforecast", ModuleType("neuralforecast"))
    monkeypatch.setitem(sys.modules, "neuralforecast.auto", auto_module)
    monkeypatch.setitem(sys.modules, "neuralforecast.losses", ModuleType("neuralforecast.losses"))
    monkeypatch.setitem(sys.modules, "neuralforecast.losses.pytorch", losses_module)
    monkeypatch.setitem(sys.modules, "neuralforecast.models", models_module)
    monkeypatch.setitem(sys.modules, "ray", ray_module)

    def run_single(config, spec, panel):
        core._construct_auto_hint(config, panel)
        return {
            "model_id": spec.model_id,
            "class_name": spec.class_name,
            "status": "SUCCEEDED",
            "certification_status": "TRAIN_ONLY",
        }

    core = _fresh_core(run_single=run_single)
    panel = pd.DataFrame(
        {
            "unique_id": ["p1", "p1", "p2", "p2"],
            "ds": [1, 2, 1, 2],
            "y": [1.0, 2.0, 2.0, 3.0],
        }
    )
    # Facade calls the core helper; use a realistic small hierarchy.
    from loto.neuralforecast import db_automodel as validation_core

    core._build_hint_panel = validation_core._build_hint_panel
    report = core._run_single_model(_config(tmp_path), _spec("AutoHINT"), panel)

    assert report["status"] == "SUCCEEDED"
    assert report["search_space_evidence"]["phase"] == "runtime_resolved"
    assert report["search_space_evidence"]["profile"]["backend"] == "ray"
    assert report["search_space_evidence"]["profile"]["categorical_count"] > 0
    assert constructor_observation["completeness"] == "COMPLETE"


def test_campaign_plan_and_summary_are_additive(tmp_path: Path) -> None:
    profile = profile_fixed_config(
        {"input_size": 4}, backend="optuna", model_name="AutoDLinear"
    )
    evidence = facade.persist_database_search_space_evidence(
        tmp_path / "models" / "nf-auto-dlinear",
        profile,
        phase="planning",
        model_id="nf-auto-dlinear",
        class_name="AutoDLinear",
        backend="optuna",
        search_seed=1,
        num_samples=4,
    )

    def run_campaign(config):
        return {
            "schema_version": "1.1.0",
            "reports": [
                {
                    "model_id": "nf-auto-dlinear",
                    "class_name": "AutoDLinear",
                    "status": "FAILED",
                    "search_space_evidence": evidence,
                }
            ],
        }

    core = _fresh_core(run_campaign=run_campaign)

    plan = core.build_campaign_plan(SimpleNamespace(), pd.DataFrame())
    result = core.run_automodel_campaign(_config(tmp_path))

    assert plan["schema_version"] == "1.1.0"
    assert plan["search_space_artifacts"]["verification"] == "read_after_write_fail_closed"
    assert result["schema_version"] == "1.1.0"
    assert result["search_space_artifact_status"] == "PASS"
    assert result["search_space_verified_model_count"] == 1
    persisted = json.loads((tmp_path / "campaign_report.json").read_text(encoding="utf-8"))
    assert persisted["search_space_artifacts"]["verified_model_count"] == 1


def test_dry_run_is_unchanged_and_installer_is_idempotent(tmp_path: Path) -> None:
    original_result = {"schema_version": "1.1.0", "status": "DRY_RUN_VERIFIED"}

    def run_campaign(config):
        return dict(original_result)

    core = _fresh_core(run_campaign=run_campaign)
    installed_run = core.run_automodel_campaign

    facade.install(core)
    result = core.run_automodel_campaign(_config(tmp_path, dry_run=True))

    assert core.run_automodel_campaign is installed_run
    assert result == original_result


def test_reinstall_recovers_originals_from_the_stable_core() -> None:
    core = _fresh_core()
    stored = dict(core._db_search_space_persistence_originals)
    facade._ORIGINALS.clear()
    facade._CORE = None

    facade.install(core)

    assert facade._CORE is core
    assert facade._ORIGINALS == stored
    assert facade._ORIGINALS["run_single_model"] is stored["run_single_model"]


def test_package_exports_keep_stable_core_class_identity() -> None:
    import loto.neuralforecast as package
    from loto.neuralforecast import db_automodel as stable_core

    assert stable_core._db_search_space_persistence_installed is True
    assert package.AutoModelCampaignConfig is stable_core.AutoModelCampaignConfig
    assert package.DatabaseTableSource is stable_core.DatabaseTableSource
    assert stable_core.AutoModelCampaignConfig.__module__ == "loto.neuralforecast.db_automodel"
    assert stable_core.DatabaseTableSource.__module__ == "loto.neuralforecast.db_automodel"
