from __future__ import annotations

import hashlib
import importlib.machinery
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from loto.neuralforecast.auto_timellm.contracts import (
    PinnedLLMIdentity,
    SnapshotFileEvidence,
)
from loto.neuralforecast.auto_timellm import runtime

REVISION = "b" * 40


def _module(name: str, *, package: bool = False) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=package)
    if package:
        module.__path__ = []
    return module


def _identity(tmp_path: Path) -> PinnedLLMIdentity:
    root = tmp_path / REVISION
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["GPT2Model"],
                "model_type": "gpt2",
                "n_embd": 64,
                "n_layer": 2,
            }
        ),
        encoding="utf-8",
    )
    (root / "tokenizer.json").write_text("{}", encoding="utf-8")
    (root / "model.safetensors").write_bytes(b"weights")
    files = []
    for name in ("config.json", "tokenizer.json", "model.safetensors"):
        path = root / name
        files.append(
            SnapshotFileEvidence(
                relative_path=name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                size_bytes=path.stat().st_size,
            )
        )
    return PinnedLLMIdentity(
        repo_id="openai-community/gpt2",
        revision=REVISION,
        snapshot_path=str(root),
        license_id="MIT",
        files=tuple(files),
    )


def _install_runtime_stubs(monkeypatch: pytest.MonkeyPatch, *, fallback: bool = False) -> None:
    neuralforecast = _module("neuralforecast", package=True)
    common = _module("neuralforecast.common", package=True)
    base_auto = _module("neuralforecast.common._base_auto")
    losses_package = _module("neuralforecast.losses", package=True)
    losses = _module("neuralforecast.losses.pytorch")
    models = _module("neuralforecast.models", package=True)
    timellm = _module("neuralforecast.models.timellm")
    ray = _module("ray", package=True)
    tune = _module("ray.tune", package=True)
    search = _module("ray.tune.search", package=True)
    basic = _module("ray.tune.search.basic_variant")
    transformers = _module("transformers", package=True)

    class BasePointLoss:
        outputsize_multiplier = 1

    class MAE(BasePointLoss):
        pass

    class BaseAuto:
        def __init__(self, **kwargs: Any) -> None:
            self.captured_kwargs = kwargs
            self.cls_model = kwargs["cls_model"]
            self.config = kwargs["config"]

        @classmethod
        def _ray_config_to_optuna(cls, config: dict[str, Any]):
            return lambda _trial: dict(config)

    class FakeTimeLLM:
        def __init__(self, **kwargs: Any) -> None:
            self.captured_kwargs = kwargs
            name = "openai-community/gpt2" if fallback else kwargs["llm"]
            self.llm_config = SimpleNamespace(_name_or_path=name)
            self.llm = SimpleNamespace(name_or_path=name)
            self.llm_tokenizer = SimpleNamespace(name_or_path=name)

    class Domain:
        def __init__(self, kind: str, value: Any) -> None:
            self.kind = kind
            self.value = value

    class BasicVariantGenerator:
        def __init__(self, random_state: int) -> None:
            self.random_state = random_state

    base_auto.BaseAuto = BaseAuto
    losses.BasePointLoss = BasePointLoss
    losses.MAE = MAE
    losses_package.pytorch = losses
    timellm.TimeLLM = FakeTimeLLM
    tune.choice = lambda value: Domain("choice", value)
    tune.loguniform = lambda low, high: Domain("loguniform", (low, high))
    tune.randint = lambda low, high: Domain("randint", (low, high))
    ray.tune = tune
    basic.BasicVariantGenerator = BasicVariantGenerator

    modules = {
        module.__name__: module
        for module in (
            neuralforecast,
            common,
            base_auto,
            losses_package,
            losses,
            models,
            timellm,
            ray,
            tune,
            search,
            basic,
            transformers,
        )
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    runtime._reset_runtime_classes_for_tests()


def _fixed_config() -> dict[str, Any]:
    return {
        "h": None,
        "architecture_profile": "compact",
        "learning_rate": 1e-4,
        "max_steps": 20,
        "val_check_steps": 10,
        "batch_size": 8,
        "windows_batch_size": 32,
        "dropout": 0.1,
        "scaler_type": "identity",
        "random_seed": 1,
    }


def test_auto_class_injects_pinned_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_runtime_stubs(monkeypatch)
    identity = _identity(tmp_path)
    auto_class = runtime.get_auto_timellm_class()
    instance = auto_class(h=1, llm_identity=identity, config=_fixed_config(), backend="ray")
    assert instance.captured_kwargs["cls_model"].__name__ == "PinnedTimeLLM"
    assert instance.config["llm_identity"]["revision"] == REVISION
    assert instance.loto_model_id == "nf-local-auto-timellm"


def test_pinned_model_derives_llm_geometry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_runtime_stubs(monkeypatch)
    identity = _identity(tmp_path)
    model_class = runtime.get_pinned_timellm_class()
    model = model_class(
        h=1,
        architecture_profile="compact",
        llm_identity=identity.model_dump(mode="json"),
        max_steps=20,
        val_check_steps=10,
        batch_size=8,
        windows_batch_size=32,
    )
    assert model.captured_kwargs["d_llm"] == 64
    assert model.captured_kwargs["enc_in"] == 1
    assert model.captured_kwargs["dec_in"] == 1
    assert model.loto_loaded_snapshot_identity["model"] == identity.snapshot_path


def test_upstream_fallback_identity_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_runtime_stubs(monkeypatch, fallback=True)
    identity = _identity(tmp_path)
    model_class = runtime.get_pinned_timellm_class()
    with pytest.raises(RuntimeError, match="does not match"):
        model_class(
            h=1,
            architecture_profile="compact",
            llm_identity=identity.model_dump(mode="json"),
            max_steps=20,
            val_check_steps=10,
            batch_size=8,
            windows_batch_size=32,
        )
