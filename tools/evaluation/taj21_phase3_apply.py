from __future__ import annotations

from pathlib import Path


TARGET = Path("src/loto/evaluation/unified_campaign.py")
TEST = Path("tests/evaluation/test_taj21_unified_probabilistic_campaign.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from loto.evaluation.metrics_general import positional_metrics\n",
        "from loto.evaluation.metrics_general import positional_metrics\n"
        "from loto.evaluation.probabilistic_oof_adapter import (\n"
        "    ProbabilisticScientificRoute,\n"
        "    build_probabilistic_scientific_plan,\n"
        "    predict_probabilistic_from_history,\n"
        ")\n",
        "probabilistic imports",
    )

    text = replace_once(
        text,
        "    baseline_id: str | None = None,\n    entry: ModelEntry | None = None,\n) -> dict[str, Any]:\n",
        "    baseline_id: str | None = None,\n"
        "    entry: ModelEntry | None = None,\n"
        "    probabilistic_route: ProbabilisticScientificRoute | None = None,\n"
        ") -> dict[str, Any]:\n",
        "evaluate_seed signature",
    )

    text = replace_once(
        text,
        "            else:\n"
        "                if entry is None:\n"
        "                    raise AssertionError(\"model entry is required\")\n"
        "                pred, metadata = _model_prediction(\n"
        "                    entry,\n"
        "                    history,\n"
        "                    prepared.geometry,\n"
        "                    config,\n"
        "                    seed=seed,\n"
        "                )\n",
        "            elif probabilistic_route is not None:\n"
        "                prediction = predict_probabilistic_from_history(\n"
        "                    history,\n"
        "                    probabilistic_route,\n"
        "                    seed=seed,\n"
        "                    protocol_hash=prepared.protocol.protocol_hash,\n"
        "                    device=config.device,\n"
        "                )\n"
        "                pred = np.asarray(prediction.values, dtype=int)\n"
        "                metadata = dict(prediction.metadata)\n"
        "            else:\n"
        "                if entry is None:\n"
        "                    raise AssertionError(\"model entry is required\")\n"
        "                pred, metadata = _model_prediction(\n"
        "                    entry,\n"
        "                    history,\n"
        "                    prepared.geometry,\n"
        "                    config,\n"
        "                    seed=seed,\n"
        "                )\n",
        "probabilistic seed route",
    )

    text = replace_once(
        text,
        "    baseline_id: str | None = None,\n    entry: ModelEntry | None = None,\n) -> dict[str, Any]:\n    seed_results: list[dict[str, Any]] = []\n",
        "    baseline_id: str | None = None,\n"
        "    entry: ModelEntry | None = None,\n"
        "    probabilistic_route: ProbabilisticScientificRoute | None = None,\n"
        ") -> dict[str, Any]:\n"
        "    if probabilistic_route is not None and not probabilistic_route.allowed:\n"
        "        unavailable_reasons = {\"BACKEND_UNAVAILABLE\", \"MODEL_BLOCKED\"}\n"
        "        unsupported_reasons = {\"TARGET_MODE_UNSUPPORTED\", \"DRAW_ORDER_REQUIRED\"}\n"
        "        if probabilistic_route.reason_code in unavailable_reasons:\n"
        "            status: Status = \"UNAVAILABLE\"\n"
        "        elif probabilistic_route.reason_code in unsupported_reasons:\n"
        "            status = \"UNSUPPORTED_GAME\"\n"
        "        else:\n"
        "            status = \"NOT_ROUTABLE\"\n"
        "        return _result_from_failure(\n"
        "            game=prepared.geometry.key,\n"
        "            candidate_id=candidate_id,\n"
        "            source=source,\n"
        "            status=status,\n"
        "            reason=f\"{probabilistic_route.reason_code}: {probabilistic_route.details}\",\n"
        "            library=library,\n"
        "            task=task,\n"
        "            protocol_hash=prepared.protocol.protocol_hash,\n"
        "        )\n"
        "    seed_results: list[dict[str, Any]] = []\n",
        "evaluate_candidate signature and route precheck",
    )

    text = replace_once(
        text,
        "                    baseline_id=baseline_id,\n                    entry=entry,\n                )\n",
        "                    baseline_id=baseline_id,\n"
        "                    entry=entry,\n"
        "                    probabilistic_route=probabilistic_route,\n"
        "                )\n",
        "evaluate_candidate pass-through",
    )

    old_selection = '''def _selected_entries(config: UnifiedCampaignConfig) -> list[ModelEntry]:
    entries = build_catalog()
    if config.model_ids is None:
        return entries
    wanted = set(config.model_ids)
    by_id = {entry.model_id: entry for entry in entries}
    missing = sorted(wanted.difference(by_id))
    if missing:
        raise KeyError(f"unknown model IDs: {missing}")
    return [entry for entry in entries if entry.model_id in wanted]


def build_campaign_plan(config: UnifiedCampaignConfig) -> list[dict[str, str]]:
    """Return the complete requested catalog x game matrix without executing models."""

    entries = _selected_entries(config)
    return [
        {
            "game": game,
            "candidate_id": entry.model_id,
            "library": entry.library,
            "task": entry.task,
        }
        for game in config.games
        for entry in entries
    ]
'''
    new_selection = '''def _selected_entries(config: UnifiedCampaignConfig) -> list[ModelEntry]:
    entries = build_catalog()
    if config.model_ids is None:
        return entries
    wanted = set(config.model_ids)
    return [entry for entry in entries if entry.model_id in wanted]


def _selected_probabilistic_routes(
    config: UnifiedCampaignConfig,
) -> list[ProbabilisticScientificRoute]:
    routes = list(build_probabilistic_scientific_plan(config.games))
    if config.model_ids is None:
        return routes
    wanted = set(config.model_ids)
    return [route for route in routes if route.model_id in wanted]


def build_campaign_plan(config: UnifiedCampaignConfig) -> list[dict[str, str]]:
    """Return the complete requested unified 250-identity x game matrix."""

    entries = _selected_entries(config)
    probabilistic_routes = _selected_probabilistic_routes(config)
    broad_ids = {entry.model_id for entry in entries}
    probabilistic_ids = {route.model_id for route in probabilistic_routes}
    collisions = sorted(broad_ids.intersection(probabilistic_ids))
    if collisions:
        raise AssertionError(f"unified scientific identity collision: {collisions}")
    if config.model_ids is not None:
        wanted = set(config.model_ids)
        missing = sorted(wanted.difference(broad_ids | probabilistic_ids))
        if missing:
            raise KeyError(f"unknown model IDs: {missing}")

    broad_rows = [
        {
            "game": game,
            "candidate_id": entry.model_id,
            "library": entry.library,
            "task": entry.task,
        }
        for game in config.games
        for entry in entries
    ]
    probabilistic_rows = [
        {
            "game": route.game,
            "candidate_id": route.model_id,
            "library": "probabilistic",
            "task": route.target_mode or "probabilistic",
        }
        for route in probabilistic_routes
    ]
    rows = broad_rows + probabilistic_rows
    pair_keys = {(row["game"], row["candidate_id"]) for row in rows}
    if len(pair_keys) != len(rows):
        raise AssertionError("unified campaign plan contains duplicate model/game pairs")
    return rows
'''
    text = replace_once(text, old_selection, new_selection, "unified selection and plan")

    text = replace_once(
        text,
        '        if row["source"] != "catalog":\n            continue\n',
        '        if row["source"] not in {"catalog", "probabilistic"}:\n            continue\n',
        "macro source inclusion",
    )

    text = replace_once(
        text,
        "    entries = _selected_entries(config)\n"
        "    plan = build_campaign_plan(config)\n"
        "    expected_pairs = len(entries) * len(config.games)\n"
        "    if len(plan) != expected_pairs:\n"
        "        raise AssertionError(\"campaign plan does not cover every requested model/game pair\")\n",
        "    entries = _selected_entries(config)\n"
        "    probabilistic_routes = _selected_probabilistic_routes(config)\n"
        "    probabilistic_ids = {route.model_id for route in probabilistic_routes}\n"
        "    plan = build_campaign_plan(config)\n"
        "    unified_models = len(entries) + len(probabilistic_ids)\n"
        "    expected_pairs = unified_models * len(config.games)\n"
        "    if len(plan) != expected_pairs:\n"
        "        raise AssertionError(\"campaign plan does not cover every requested model/game pair\")\n",
        "run plan counts",
    )

    text = replace_once(
        text,
        "        for entry in entries:\n"
        "            results.append(\n"
        "                _evaluate_candidate(\n"
        "                    context,\n"
        "                    config,\n"
        "                    candidate_id=entry.model_id,\n"
        "                    source=\"catalog\",\n"
        "                    library=entry.library,\n"
        "                    task=entry.task,\n"
        "                    entry=entry,\n"
        "                )\n"
        "            )\n\n"
        "    catalog_results = [row for row in results if row[\"source\"] == \"catalog\"]\n"
        "    if len(catalog_results) != expected_pairs:\n"
        "        raise AssertionError(\"result matrix lost one or more model/game combinations\")\n"
        "    pair_keys = {(row[\"game\"], row[\"candidate_id\"]) for row in catalog_results}\n",
        "        for entry in entries:\n"
        "            results.append(\n"
        "                _evaluate_candidate(\n"
        "                    context,\n"
        "                    config,\n"
        "                    candidate_id=entry.model_id,\n"
        "                    source=\"catalog\",\n"
        "                    library=entry.library,\n"
        "                    task=entry.task,\n"
        "                    entry=entry,\n"
        "                )\n"
        "            )\n"
        "        for route in probabilistic_routes:\n"
        "            if route.game != game:\n"
        "                continue\n"
        "            results.append(\n"
        "                _evaluate_candidate(\n"
        "                    context,\n"
        "                    config,\n"
        "                    candidate_id=route.model_id,\n"
        "                    source=\"probabilistic\",\n"
        "                    library=\"probabilistic\",\n"
        "                    task=route.target_mode or \"probabilistic\",\n"
        "                    probabilistic_route=route,\n"
        "                )\n"
        "            )\n\n"
        "    catalog_results = [\n"
        "        row for row in results if row[\"source\"] in {\"catalog\", \"probabilistic\"}\n"
        "    ]\n"
        "    if len(catalog_results) != expected_pairs:\n"
        "        raise AssertionError(\"result matrix lost one or more model/game combinations\")\n"
        "    pair_keys = {(row[\"game\"], row[\"candidate_id\"]) for row in catalog_results}\n",
        "run probabilistic execution",
    )

    text = replace_once(
        text,
        '        "catalog_models": len(entries),\n',
        '        "catalog_models": unified_models,\n'
        '        "broad_catalog_models": len(entries),\n'
        '        "probabilistic_catalog_models": len(probabilistic_ids),\n',
        "summary model counts",
    )

    TARGET.write_text(text, encoding="utf-8")

    TEST.write_text(
        '''from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pandas as pd

from loto.evaluation import unified_campaign as campaign
from loto.evaluation.probabilistic_oof_adapter import (
    ProbabilisticOOFPrediction,
    ProbabilisticScientificRoute,
)
from loto.game.geometry import geometry_for


def _config(tmp_path, *, model_ids=None):
    return campaign.UnifiedCampaignConfig(
        output_dir=tmp_path / "run",
        git_commit="a" * 40,
        model_ids=model_ids,
        seeds=(42,),
        folds=1,
        test_size=1,
        min_train_size=10,
        holdout_size=0,
    )


def test_default_plan_is_exact_unified_250_by_6(tmp_path) -> None:
    config = _config(tmp_path)
    plan = campaign.build_campaign_plan(config)
    assert len(plan) == 1500
    assert len({(row["game"], row["candidate_id"]) for row in plan}) == 1500
    assert sum(row["library"] == "probabilistic" for row in plan) == 456
    assert sum(row["library"] != "probabilistic" for row in plan) == 1044
    assert len({row["candidate_id"] for row in plan}) == 250


def test_probabilistic_model_id_subset_routes_all_six_games(tmp_path) -> None:
    config = _config(tmp_path, model_ids=("pp-multinomial-dglm",))
    plan = campaign.build_campaign_plan(config)
    assert len(plan) == 6
    assert {row["candidate_id"] for row in plan} == {"pp-multinomial-dglm"}
    assert {row["game"] for row in plan} == set(config.games)
    assert {row["library"] for row in plan} == {"probabilistic"}


def test_probabilistic_seed_uses_history_only_and_scores_after_lock(tmp_path, monkeypatch) -> None:
    geometry = geometry_for("numbers3")
    frame = pd.DataFrame(
        {
            "draw_no": np.arange(1, 14),
            "d1": np.arange(13) % 10,
            "d2": (np.arange(13) + 2) % 10,
            "d3": (np.arange(13) + 4) % 10,
        }
    )
    fold = SimpleNamespace(fold_id=0, test_start=12, test_end=13)
    prepared = campaign.PreparedGame(
        geometry=geometry,
        development=frame,
        holdout_rows=0,
        folds=(fold,),
        protocol=SimpleNamespace(protocol_hash="b" * 64),
    )
    route = ProbabilisticScientificRoute(
        model_id="pp-multinomial-dglm",
        family="state_space",
        game="numbers3",
        target_mode="dynamic_multinomial",
        backend="builtin",
        inference_profile_id=None,
        resource_class="heavy_cpu",
        allowed=True,
        reason_code="ALLOWED",
        details=("target_mode=dynamic_multinomial",),
    )
    observed = {"history_rows": None, "sealed": False}

    def fake_predict(history, _route, **kwargs):
        observed["history_rows"] = len(history)
        assert kwargs["protocol_hash"] == "b" * 64
        return ProbabilisticOOFPrediction(
            values=(1, 2, 3),
            probabilities=np.full((3, 10), 0.1),
            metadata={"route": "probabilistic-test"},
        )

    def fake_lock(*args, **kwargs):
        observed["sealed"] = True
        return {"path": str(tmp_path / "lock.json"), "sha256": "c" * 64}

    def fake_metrics(actual, predicted, geometry, *, tau):
        assert observed["sealed"] is True
        return {
            "hit_at_1": 1.0,
            "position_hit_at_1": 1.0,
            "position_hit_at_1_by_position": {"1": 1.0, "2": 1.0, "3": 1.0},
            "all_positions_hit_at_1": 1.0,
            "mae": 0.0,
            "mse": 0.0,
            "rmse": 0.0,
        }

    monkeypatch.setattr(campaign, "predict_probabilistic_from_history", fake_predict)
    monkeypatch.setattr(campaign, "_write_prediction_lock", fake_lock)
    monkeypatch.setattr(campaign, "_canonical_metrics", fake_metrics)

    result = campaign._evaluate_seed(
        prepared,
        route.model_id,
        42,
        _config(tmp_path),
        probabilistic_route=route,
    )
    assert observed["history_rows"] == 12
    assert observed["sealed"] is True
    assert result["metrics"]["hit_at_1"] == 1.0

    source = inspect.getsource(campaign._evaluate_seed)
    assert source.index("lock = _write_prediction_lock") < source.index("actual = np.asarray")


def test_disallowed_probabilistic_route_is_explicit_without_execution(tmp_path, monkeypatch) -> None:
    geometry = geometry_for("numbers3")
    frame = pd.DataFrame(
        {"draw_no": [1], "d1": [1], "d2": [2], "d3": [3]}
    )
    prepared = campaign.PreparedGame(
        geometry=geometry,
        development=frame,
        holdout_rows=0,
        folds=(),
        protocol=SimpleNamespace(protocol_hash="d" * 64),
    )
    route = ProbabilisticScientificRoute(
        model_id="blocked-probabilistic",
        family="test",
        game="numbers3",
        target_mode=None,
        backend="missing",
        inference_profile_id=None,
        resource_class=None,
        allowed=False,
        reason_code="BACKEND_UNAVAILABLE",
        details=("backend unavailable",),
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("disallowed route must not execute")

    monkeypatch.setattr(campaign, "_evaluate_seed", should_not_run)
    result = campaign._evaluate_candidate(
        prepared,
        _config(tmp_path),
        candidate_id=route.model_id,
        source="probabilistic",
        library="probabilistic",
        task="probabilistic",
        probabilistic_route=route,
    )
    assert result["status"] == "UNAVAILABLE"
    assert "BACKEND_UNAVAILABLE" in result["reason"]
''',
        encoding="utf-8",
    )

    print("TAJ21_PHASE3_PATCH=PASS")


if __name__ == "__main__":
    main()
