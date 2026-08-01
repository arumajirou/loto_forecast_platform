import inspect

import pytest
from neuralforecast import auto

from loto.models.catalog import get_model_spec
from loto.models.neuralforecast_adapter import (
    MODELS_REQUIRING_N_SERIES,
    AutoModelRequest,
    resolve_auto_model_plan,
)


@pytest.mark.parametrize(
    ("model_id", "class_name"),
    [
        ("nf-auto-softssharp", "AutoSOFTSSharp"),
        ("nf-auto-xlinear", "AutoXLinear"),
        ("nf-auto-xlstm", "AutoxLSTM"),
    ],
)
def test_new_auto_models_are_catalogued(
    model_id: str,
    class_name: str,
) -> None:
    spec = get_model_spec(model_id)

    assert spec.class_name == class_name
    assert spec.library == "neuralforecast_auto"
    assert getattr(auto, class_name) is not None


@pytest.mark.parametrize(
    "class_name",
    [
        "AutoSOFTSSharp",
        "AutoXLinear",
    ],
)
def test_multivariate_auto_models_require_n_series(
    class_name: str,
) -> None:
    assert class_name in MODELS_REQUIRING_N_SERIES

    with pytest.raises(
        ValueError,
        match="requires n_series",
    ):
        resolve_auto_model_plan(
            AutoModelRequest(
                model_name=class_name,
                h=1,
                backend="optuna",
            )
        )


@pytest.mark.parametrize(
    "class_name",
    [
        "AutoSOFTSSharp",
        "AutoXLinear",
    ],
)
def test_multivariate_auto_models_receive_n_series(
    class_name: str,
) -> None:
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name=class_name,
            h=1,
            backend="optuna",
            num_samples=1,
            n_series=7,
            config={
                "input_size": 8,
                "max_steps": 2,
            },
        )
    )

    assert plan.constructor_kwargs["n_series"] == 7
    assert plan.config["n_series"] == 7


def test_autoxlstm_does_not_require_n_series() -> None:
    assert "AutoxLSTM" not in MODELS_REQUIRING_N_SERIES

    signature = inspect.signature(auto.AutoxLSTM)

    assert "n_series" not in signature.parameters

    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoxLSTM",
            h=1,
            backend="optuna",
            num_samples=1,
            config={
                "input_size": 8,
                "max_steps": 2,
            },
        )
    )

    assert "n_series" not in plan.constructor_kwargs
