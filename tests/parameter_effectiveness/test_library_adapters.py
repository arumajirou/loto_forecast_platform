from __future__ import annotations

from loto.parameter_effectiveness.adapters import default_registry
from loto.parameter_effectiveness.contracts import (
    EffectOutcome,
    EffectSurface,
    ExpectedRelation,
    ParameterProbeSpec,
    ParameterScope,
)
from loto.parameter_effectiveness.core import evaluate_probe


def test_mlforecast_num_samples_changes_real_trial_count() -> None:
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

    assert result.outcome is EffectOutcome.EFFECTIVE
    assert result.pairs_eligible == 2
    assert result.pairs_matched == 2
    assert all(pair.control.finite for pair in result.paired)
    assert all(pair.treatment.finite for pair in result.paired)
    assert all(pair.control.output_shape for pair in result.paired)
    assert all(pair.treatment.output_shape for pair in result.paired)


def test_statsforecast_season_length_changes_real_predictions() -> None:
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

    assert result.outcome is EffectOutcome.EFFECTIVE
    assert result.pairs_eligible == 2
    assert result.pairs_matched == 2
    assert all(pair.control.finite for pair in result.paired)
    assert all(pair.treatment.finite for pair in result.paired)
    assert all(pair.control.prediction_sha256 for pair in result.paired)
    assert all(pair.treatment.prediction_sha256 for pair in result.paired)
