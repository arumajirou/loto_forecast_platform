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


def test_live_scientific_preflight_freezes_exact_250x6_gap(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "taj21-preflight"

    result = module.build_preflight(output)

    assert result["status"] == "PASS"
    assert result["inventory"] == {
        "broad_identities": 174,
        "probabilistic_identities": 76,
        "unified_identities": 250,
        "games": 6,
        "current_scientific_identities": 174,
        "current_scientific_pairs": 1044,
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
    assert gap["missing_identity_count"] == 76
    assert gap["missing_model_game_pairs"] == 456
    assert gap["execution_readiness"] == "BLOCKED"
    assert gap["blocking_reasons"] == ["PROBABILISTIC_76_OOF_ADAPTER_MISSING"]
    assert len(gap["missing_scientific_identities"]) == 76

    assert result["scientific_boundary"] == {
        "development_oof": "PLANNED",
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
    assert result["inventory"]["current_scientific_pairs"] == 1044


def test_preflight_source_contract_detects_broad_only_campaign() -> None:
    module = load_module()

    seeds, surface = module._current_scientific_contract()

    assert seeds == (42, 1729, 20260730)
    assert surface == "broad-only"
