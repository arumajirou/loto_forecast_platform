from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "evaluation" / "taj21_scientific_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("taj21_scientific_preflight", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_scientific_preflight_freezes_exact_250x6_ready_surface(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "taj21-preflight"

    result = module.build_preflight(output)

    assert result["schema_version"] == "taj21-scientific-preflight/v2"
    assert result["status"] == "PASS"
    assert result["inventory"] == {
        "broad_identities": 174,
        "probabilistic_identities": 76,
        "unified_identities": 250,
        "games": 6,
        "current_scientific_identities": 250,
        "current_scientific_pairs": 1500,
        "target_unified_pairs": 1500,
    }
    assert result["target_plan_rows"] == 1500
    assert result["primary_metric"] == "hit_at_1"
    assert result["required_metrics"] == [
        "hit_at_1",
        "position_hit_at_1",
        "all_positions_hit_at_1",
        "mae",
        "mse",
        "rmse",
    ]
    assert result["required_baselines"] == [
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "statistical_ar1",
    ]
    assert result["seed_inventory"] == [42, 1729, 20260730]

    gap = result["route_gap"]
    assert gap["missing_identity_count"] == 0
    assert gap["missing_model_game_pairs"] == 0
    assert gap["historical_incremental_model_game_pairs"] == 456
    assert gap["execution_readiness"] == "PASS"
    assert gap["blocking_reasons"] == []
    assert gap["missing_scientific_identities"] == []
    assert gap["current_scientific_surface"] == "unified-250"
    assert all(gap["source_contract_checks"].values())

    assert result["scientific_boundary"] == {
        "development_oof": "EXECUTION_READY",
        "holdout": "CLOSED",
        "prospective": "CLOSED",
        "promotion": "CLOSED",
        "accuracy_claim": False,
    }
    for name in (
        "SCIENTIFIC_PREFLIGHT.json",
        "UNIFIED_SCIENTIFIC_PLAN.json",
        "SCIENTIFIC_ROUTE_GAP.json",
        "VERIFICATION_REPORT.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    ):
        assert (output / name).is_file()


def test_preflight_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "taj21-preflight"
    output.mkdir()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module.build_preflight(output)


def test_preflight_does_not_import_runtime_campaign_or_sklearn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    output = tmp_path / "dependency-free-preflight"
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "loto.evaluation.unified_campaign" or name.startswith("sklearn"):
            raise AssertionError(f"preflight attempted forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = module.build_preflight(output)

    assert result["status"] == "PASS"
    assert result["inventory"]["current_scientific_pairs"] == 1500
    assert result["route_gap"]["execution_readiness"] == "PASS"


def test_preflight_source_contract_detects_unified_campaign_and_lock_order() -> None:
    module = load_module()

    seeds, surface, checks = module._current_scientific_contract()

    assert seeds == (42, 1729, 20260730)
    assert surface == "unified-250"
    assert checks == {
        "broad_selector_from_build_catalog": True,
        "probabilistic_selector_from_scientific_plan": True,
        "planner_uses_broad_selector": True,
        "planner_uses_probabilistic_selector": True,
        "runtime_uses_probabilistic_selector": True,
        "history_only_probabilistic_predictor": True,
        "durable_prediction_lock_present": True,
        "prediction_lock_before_actual": True,
    }


def test_preflight_fails_closed_when_lock_moves_after_actual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    source_path = tmp_path / "unified_campaign.py"
    source_path.write_text(
        """
class UnifiedCampaignConfig:
    seeds: tuple[int, ...] = (42, 1729, 20260730)


def _selected_entries(config):
    return build_catalog()


def _selected_probabilistic_routes(config):
    return build_probabilistic_scientific_plan(config.games)


def build_campaign_plan(config):
    return _selected_entries(config), _selected_probabilistic_routes(config)


def _evaluate_seed(history):
    prediction = predict_probabilistic_from_history(history)
    actual = values[0]
    lock = _write_prediction_lock(prediction)
    return actual, lock


def run_unified_campaign(config):
    return _selected_probabilistic_routes(config)
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "UNIFIED_CAMPAIGN_SOURCE", source_path)

    with pytest.raises(
        module.ScientificPreflightError,
        match="execution contract is incomplete",
    ):
        module._current_scientific_contract()
