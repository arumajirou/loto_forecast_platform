from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import torch

from loto.auto_campaign.p1_compat import (
    load_trial_checkpoint_for_verification,
    normalize_persistent_auto_class_names,
    sanitize_model_config,
    save_trial_checkpoint,
)


class TinyModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = torch.nn.Linear(2, 1)
        self.trainer = None


def test_decoder_models_raise_input_size_to_two() -> None:
    config = {
        "h": 1,
        "input_size": 1,
        "decoder_input_size_multiplier": 0.5,
        "deterministic": True,
    }

    actual = sanitize_model_config(
        config,
        model_name="Autoformer",
    )

    assert actual["input_size"] == 2
    assert actual["deterministic"] == "warn"
    assert config["input_size"] == 1


def test_nbeats_h1_uses_identity_stack() -> None:
    actual = sanitize_model_config(
        {"h": 1, "input_size": 4},
        model_name="NBEATS",
    )

    assert actual["stack_types"] == ["identity"]
    assert actual["n_blocks"] == [1]


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    model = TinyModel()
    path = tmp_path / "model.ckpt"

    payload = {
        "state_dict": model.state_dict(),
        "hyper_parameters": {},
    }
    save_trial_checkpoint(
        model=model,
        checkpoint_path=path,
        fallback_payload=payload,
    )

    raw = torch.load(
        path,
        map_location="cpu",
        weights_only=False,
    )
    assert "pytorch-lightning_version" in raw
    assert "state_dict" in raw

    loaded = load_trial_checkpoint_for_verification(
        model=model,
        checkpoint_path=path,
    )

    for expected, actual in zip(
        model.parameters(),
        loaded.parameters(),
        strict=True,
    ):
        assert torch.equal(expected, actual)


def test_persistent_class_name_is_normalized() -> None:
    class AutoDummy:
        pass

    class PersistentAutoDummy(AutoDummy):
        pass

    model = PersistentAutoDummy()
    nf = SimpleNamespace(models=[model])

    changes = normalize_persistent_auto_class_names(nf)

    assert changes == [
        {
            "from": "PersistentAutoDummy",
            "to": "AutoDummy",
        }
    ]
    assert type(model).__name__ == "AutoDummy"


def test_runtime_install_does_not_patch_base_auto() -> None:
    from neuralforecast.common._base_auto import BaseAuto

    from loto.auto_campaign.p1_compat import (
        install_p1_runtime_compatibility,
    )

    before = BaseAuto._fit_model
    install_p1_runtime_compatibility()
    after = BaseAuto._fit_model

    assert after is before
