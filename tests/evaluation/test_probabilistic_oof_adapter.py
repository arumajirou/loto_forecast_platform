from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.evaluation import probabilistic_oof_adapter as adapter
from loto.game.geometry import known_games
from loto.probabilistic.catalog import list_probabilistic_model_specs


def _numbers3_history(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": np.arange(1, rows + 1),
            "N1": np.arange(rows) % 10,
            "N2": (np.arange(rows) + 2) % 10,
            "N3": (np.arange(rows) + 4) % 10,
        }
    )


def test_probabilistic_scientific_plan_covers_exact_76x6_matrix() -> None:
    routes = adapter.build_probabilistic_scientific_plan()
    model_ids = {spec.model_id for spec in list_probabilistic_model_specs()}
    games = tuple(known_games())

    assert len(model_ids) == 76
    assert len(games) == 6
    assert len(routes) == 456
    assert len({(route.game, route.model_id) for route in routes}) == 456
    assert {route.model_id for route in routes} == model_ids
    assert {route.game for route in routes} == set(games)
    assert all(route.reason_code for route in routes)
    assert all(route.backend for route in routes)
    assert all(route.target_mode is not None for route in routes if route.allowed)


def test_prediction_bundle_contains_history_only_before_actual_read(monkeypatch) -> None:
    route = adapter.resolve_probabilistic_scientific_route("pp-multinomial-dglm", "numbers3")
    assert route.allowed
    history = _numbers3_history()
    observed: dict[str, int] = {}

    def fake_fit_predict_once(**kwargs):
        bundle = kwargs["bundle"]
        observed["bundle_rows"] = bundle.rows
        observed["train_end"] = kwargs["train_end"]
        probability_draws = np.full((8, 3, 10), 0.1, dtype=float)
        posterior = SimpleNamespace(draw_count=8, probability_draws=probability_draws)
        mean = np.full((3, 10), 0.1, dtype=float)
        decoded = [1, 2, 3]
        diagnostics = {"status": "PASS", "failure_codes": []}
        return posterior, mean, pd.DataFrame(), decoded, {}, diagnostics

    monkeypatch.setattr(adapter, "_fit_predict_once", fake_fit_predict_once)
    result = adapter.predict_probabilistic_from_history(
        history,
        route,
        seed=42,
        protocol_hash="a" * 64,
        device="cpu",
    )

    assert observed == {"bundle_rows": len(history), "train_end": len(history)}
    assert result.values == (1, 2, 3)
    assert result.metadata["history_rows"] == len(history)
    assert result.metadata["target_actual_present_in_fit_bundle"] is False
    assert result.metadata["target_actual_read"] is False


def test_prediction_only_route_rejects_unexpected_target_metrics(monkeypatch) -> None:
    route = adapter.resolve_probabilistic_scientific_route("pp-multinomial-dglm", "numbers3")
    assert route.allowed

    def fake_fit_predict_once(**kwargs):
        posterior = SimpleNamespace(draw_count=4)
        mean = np.full((3, 10), 0.1, dtype=float)
        return posterior, mean, pd.DataFrame(), [1, 2, 3], {"hit_at_1": 1.0}, {"status": "PASS"}

    monkeypatch.setattr(adapter, "_fit_predict_once", fake_fit_predict_once)
    with pytest.raises(adapter.ProbabilisticScientificRouteError, match="unexpectedly evaluated"):
        adapter.predict_probabilistic_from_history(
            _numbers3_history(),
            route,
            seed=42,
            protocol_hash="b" * 64,
            device="cpu",
        )


def test_disallowed_route_fails_before_fit(monkeypatch) -> None:
    route = adapter.ProbabilisticScientificRoute(
        model_id="pp-multinomial-dglm",
        family="state_space",
        game="numbers3",
        target_mode="dynamic_multinomial",
        backend="builtin",
        inference_profile_id=None,
        resource_class=None,
        allowed=False,
        reason_code="MODEL_BLOCKED",
        details=("test",),
    )

    def fail_if_called(**kwargs):
        raise AssertionError("fit must not be called")

    monkeypatch.setattr(adapter, "_fit_predict_once", fail_if_called)
    with pytest.raises(adapter.ProbabilisticScientificRouteError, match="not executable"):
        adapter.predict_probabilistic_from_history(
            _numbers3_history(),
            route,
            seed=42,
            protocol_hash="c" * 64,
            device="cpu",
        )
