from __future__ import annotations

import pytest

from loto.adapters.autogluon.api_contract import (
    AutoGluonApiContractError,
    validate_hpo_tune_kwargs,
    validate_public_api_kwargs,
)


def test_hpo_presets_match_autogluon_1_5_public_api() -> None:
    validate_hpo_tune_kwargs("auto")
    validate_hpo_tune_kwargs("random")


def test_hpo_dictionary_requires_all_documented_keys() -> None:
    with pytest.raises(AutoGluonApiContractError, match="missing required keys"):
        validate_hpo_tune_kwargs({"num_trials": 2})


def test_hpo_dictionary_accepts_local_random_contract() -> None:
    value = {"num_trials": 2, "scheduler": "local", "searcher": "random"}
    validate_hpo_tune_kwargs(value)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"num_trials": 0, "scheduler": "local", "searcher": "random"}, "positive"),
        ({"num_trials": 2, "scheduler": "fifo", "searcher": "random"}, "scheduler"),
        ({"num_trials": 2, "scheduler": "local", "searcher": "grid"}, "searcher"),
        (
            {
                "num_trials": 2,
                "scheduler": "local",
                "searcher": "random",
                "unknown": True,
            },
            "unsupported keys",
        ),
    ],
)
def test_hpo_dictionary_rejects_unsupported_values(value: dict, message: str) -> None:
    with pytest.raises(AutoGluonApiContractError, match=message):
        validate_hpo_tune_kwargs(value)


def test_public_api_guard_accepts_generated_keyword_sets() -> None:
    validate_public_api_kwargs(
        predictor_kwargs={"target": "target", "prediction_length": 1, "path": "/tmp/model"},
        fit_kwargs={"hyperparameters": {"Naive": {}}, "random_seed": 1},
        predict_kwargs={"random_seed": 1},
    )


def test_public_api_guard_rejects_unknown_fit_keyword() -> None:
    with pytest.raises(AutoGluonApiContractError, match="unsupported"):
        validate_public_api_kwargs(
            predictor_kwargs={"target": "target"},
            fit_kwargs={"not_a_real_fit_argument": True},
        )


def test_direct_hpo_validator_rejects_unknown_string_preset() -> None:
    with pytest.raises(AutoGluonApiContractError, match="must be one of"):
        validate_hpo_tune_kwargs("bayes")
