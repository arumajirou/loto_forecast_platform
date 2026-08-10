from __future__ import annotations

from types import SimpleNamespace

from loto.statsforecast.real_game_preflight import (
    build_preflight_matrix,
    summarize_preflight,
)


class FakeARIMA:
    def __init__(self, order):
        self.order = order


class FakeSklearnModel:
    def __init__(self, model):
        self.model = model


class FakeNaNModel:
    pass


def _entry(class_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        model_id=f"sf-{class_name.lower()}",
        family="test",
        library="statsforecast",
        task="position_series",
        class_name=class_name,
        priority="p1",
        package="statsforecast",
        capabilities=("position",),
        default_params={},
        notes="",
    )


def test_preflight_retains_all_scientific_lanes() -> None:
    entries = [
        _entry("ARIMA"),
        _entry("SklearnModel"),
        _entry("NaNModel"),
    ]
    models_module = SimpleNamespace(
        ARIMA=FakeARIMA,
        SklearnModel=FakeSklearnModel,
        NaNModel=FakeNaNModel,
    )

    rows = build_preflight_matrix(entries, models_module)

    assert len(rows) == 3
    assert [row["lane"] for row in rows] == [
        "UNIVARIATE",
        "EXOGENOUS",
        "EXPECTED_NEGATIVE_CONTROL",
    ]
    assert all(row["construct_status"] == "VERIFIED" for row in rows)
    assert rows[0]["resolved_parameters"] == {"order": (1, 0, 0)}
    assert rows[0]["primary_univariate_eligible"] is True
    assert rows[1]["primary_univariate_eligible"] is False
    assert rows[2]["primary_univariate_eligible"] is False


def test_summary_can_verify_an_explicit_inventory_contract() -> None:
    rows = [
        {
            "model_id": "sf-arima",
            "model_name": "ARIMA",
            "lane": "UNIVARIATE",
            "construct_status": "VERIFIED",
        },
        {
            "model_id": "sf-sklearnmodel",
            "model_name": "SklearnModel",
            "lane": "EXOGENOUS",
            "construct_status": "VERIFIED",
        },
        {
            "model_id": "sf-nanmodel",
            "model_name": "NaNModel",
            "lane": "EXPECTED_NEGATIVE_CONTROL",
            "construct_status": "VERIFIED",
        },
    ]

    summary = summarize_preflight(
        rows,
        expected_model_count=3,
        expected_univariate=1,
        expected_exogenous=1,
        expected_negative_control=1,
        statsforecast_version="2.1.1",
    )

    assert summary["construct_verified"] == 3
    assert summary["construct_failed"] == 0
    assert summary["lane_counts"] == {
        "UNIVARIATE": 1,
        "EXOGENOUS": 1,
        "EXPECTED_NEGATIVE_CONTROL": 1,
    }
    assert summary["failed_models"] == []
    assert summary["formal_pass"] is True


def test_summary_is_fail_visible_when_constructor_fails() -> None:
    rows = [
        {
            "model_id": "sf-broken",
            "model_name": "Broken",
            "lane": "UNIVARIATE",
            "construct_status": "EXECUTION_FAILED",
            "error_type": "TypeError",
            "error": "missing required argument",
        }
    ]

    summary = summarize_preflight(
        rows,
        expected_model_count=1,
        expected_univariate=1,
        expected_exogenous=0,
        expected_negative_control=0,
        statsforecast_version="2.1.1",
    )

    assert summary["construct_verified"] == 0
    assert summary["construct_failed"] == 1
    assert summary["formal_pass"] is False
    assert summary["failed_models"] == [
        {
            "model_id": "sf-broken",
            "model_name": "Broken",
            "error_type": "TypeError",
            "error": "missing required argument",
        }
    ]
