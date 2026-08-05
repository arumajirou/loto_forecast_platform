from __future__ import annotations

from typing import Any

from loto.auto_campaign.p1_compat import (
    prepare_auto_model_config,
    sanitize_model_config,
    save_neuralforecast_compat,
)


class DummyAuto:
    def __init__(self, config: Any, cls_name: str) -> None:
        self.config = config
        self.cls_model = type(cls_name, (), {})


def test_prepare_ray_config_before_fit() -> None:
    auto = DummyAuto(
        {
            "h": 1,
            "input_size": 1,
            "decoder_input_size_multiplier": 0.5,
            "deterministic": True,
        },
        "Autoformer",
    )

    requested = prepare_auto_model_config(
        auto,
        dict(auto.config),
        model_name="AutoAutoformer",
    )

    assert requested["input_size"] == 2
    assert requested["deterministic"] == "warn"
    assert auto.config["input_size"] == 2
    assert auto.config["deterministic"] == "warn"


def test_prepare_optuna_callable_before_trial() -> None:
    def provider(trial: Any) -> dict[str, Any]:
        del trial
        return {
            "h": 1,
            "input_size": 1,
            "deterministic": True,
        }

    auto = DummyAuto(provider, "BiTCN")

    prepare_auto_model_config(
        auto,
        provider,
        model_name="AutoBiTCN",
    )

    actual = auto.config(object())

    assert actual["input_size"] == 2
    assert actual["deterministic"] == "warn"


def test_h1_model_specific_configs() -> None:
    nbeats = sanitize_model_config(
        {"h": 1, "input_size": 1},
        model_name="NBEATS",
    )
    assert nbeats["stack_types"] == ["identity"]
    assert nbeats["n_blocks"] == [1]
    assert nbeats["mlp_units"] == [[64, 64]]

    timesnet = sanitize_model_config(
        {"h": 1, "input_size": 1, "top_k": 5},
        model_name="TimesNet",
    )
    assert timesnet["input_size"] == 4
    assert timesnet["top_k"] == 1

    timexer = sanitize_model_config(
        {"h": 1, "input_size": 1, "patch_len": 16},
        model_name="TimeXer",
    )
    assert timexer["input_size"] == 16


def test_compat_save_restores_dynamic_class_name() -> None:
    class AutoDummy:
        pass

    class PersistentTrialMixin:
        pass

    class PersistentAutoDummy(
        PersistentTrialMixin,
        AutoDummy,
    ):
        pass

    model = PersistentAutoDummy()
    seen: list[str] = []

    class DummyForecast:
        models = [model]

        def save(self, *args: Any, **kwargs: Any) -> str:
            del args, kwargs
            seen.append(type(model).__name__)
            return "saved"

    nf = DummyForecast()
    result = save_neuralforecast_compat(
        nf,
        "/tmp/example",
        overwrite=True,
    )

    assert result == "saved"
    assert seen == ["AutoDummy"]
    assert type(model).__name__ == "PersistentAutoDummy"
