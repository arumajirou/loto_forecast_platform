from __future__ import annotations

import os

import pytest

from loto.parameter_effectiveness.adapters import default_registry
from loto.parameter_effectiveness.contracts import (
    EffectOutcome,
    EffectSurface,
    ExpectedRelation,
    ParameterProbeResult,
    ParameterProbeSpec,
    ParameterScope,
)
from loto.parameter_effectiveness.core import evaluate_probe

_REQUIRE_REAL_ADAPTERS = os.getenv("LOTO_REQUIRE_REAL_PARAMETER_ADAPTERS") == "1"


def _require_supported_or_skip(result: ParameterProbeResult) -> None:
    if result.outcome is not EffectOutcome.UNSUPPORTED:
        return
    message = f"real parameter adapter unavailable: {result.support_reason or result.library}"
    if _REQUIRE_REAL_ADAPTERS:
        pytest.fail(message)
    pytest.skip(message)


def test_mlforecast_num_samples_changes_real_trial_count() -> None:
    pytest.importorskip("mlforecast")

    probe = ParameterProbeSpec(
        probe_id="mlforecast-num-samples",
        library="mlforecast",
        model="AutoLinearRegression",
        parameter="num_samples",
        scope=ParameterScope.FIT,
        control=1,
        treatment=2,
        expected_surface=EffectSurface.TRIAL_COUNT,
        expected_relation=ExpectedRelation.INCREASE,
        seeds=(1, 42),
        repeats=1,
        min_match_fraction=1.0,
        base_args={
            "n_windows": 2,
            "h": 1,
            "step_size": 1,
            "input_size": 48,
            "refit": False,
        },
    )

    result = evaluate_probe(probe, default_registry())
    _require_supported_or_skip(result)

    assert result.outcome is EffectOutcome.EFFECTIVE
    assert result.pairs_eligible == 2
    assert result.pairs_matched == 2
    assert all(pair.control.finite for pair in result.paired)
    assert all(pair.treatment.finite for pair in result.paired)
    assert all(pair.control.output_shape for pair in result.paired)
    assert all(pair.treatment.output_shape for pair in result.paired)


def test_statsforecast_season_length_changes_real_predictions() -> None:
    pytest.importorskip("statsforecast")

    probe = ParameterProbeSpec(
        probe_id="statsforecast-season-length",
        library="statsforecast",
        model="SeasonalNaive",
        parameter="season_length",
        scope=ParameterScope.MODEL_CONSTRUCTOR,
        control=2,
        treatment=7,
        expected_surface=EffectSurface.PREDICTION,
        expected_relation=ExpectedRelation.CHANGE,
        seeds=(1, 42),
        repeats=1,
        min_match_fraction=1.0,
        base_args={"h": 7, "train_length": 84, "freq": "D", "n_jobs": 1},
    )

    result = evaluate_probe(probe, default_registry())
    _require_supported_or_skip(result)

    assert result.outcome is EffectOutcome.EFFECTIVE
    assert result.pairs_eligible == 2
    assert result.pairs_matched == 2
    assert all(pair.control.finite for pair in result.paired)
    assert all(pair.treatment.finite for pair in result.paired)
    assert all(pair.control.prediction_sha256 for pair in result.paired)
    assert all(pair.treatment.prediction_sha256 for pair in result.paired)
