"""Fix 1 regression tests: `NeuralForecast(models=[...])` deep-copies its inputs.

`nf.models[0]` is never the caller's pre-construction AutoModel reference, so
all post-fit inspection/persistence must rebind to the fitted object that
`runner.py::_require_single_fitted_model` returns. These tests exercise the
real `neuralforecast` API (no mocking of NeuralForecast/AutoModel behavior)
to verify the deep-copy premise and the guard built on top of it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from loto.auto_campaign.persistence import save_best_model_bundle
from loto.auto_campaign.runner import _require_single_fitted_model


def _tiny_panel() -> pd.DataFrame:
    # This platform's AutoModel campaign uses integer draw-sequence `ds`
    # values with freq=1 (see contracts.py CampaignConfig.freq), not
    # calendar dates -- persistence.py's train_contract.json writer calls
    # int(train_panel["ds"].min()/.max()) directly.
    rng = np.random.default_rng(0)
    n = 40
    return pd.DataFrame(
        {
            "unique_id": "series_1",
            "ds": np.arange(n, dtype=np.int64),
            "y": rng.normal(size=n).cumsum() + 50,
        }
    )


@pytest.fixture(scope="module")
def fitted_auto_dlinear() -> dict[str, Any]:
    """Fit a real AutoDLinear (optuna, num_samples=1, CPU, 2 steps) once.

    Mirrors the exact object-identity bug this fix addresses: the original
    `auto_model` reference passed into `NeuralForecast(models=[...])` is
    never the object that gets fit.
    """
    from neuralforecast import NeuralForecast
    from neuralforecast.auto import AutoDLinear
    from neuralforecast.losses.pytorch import MAE

    def config(trial: Any) -> dict[str, Any]:
        return {
            "input_size": 8,
            "max_steps": 2,
            "val_check_steps": 1,
            "hist_exog_list": [],
        }

    auto_model = AutoDLinear(
        h=4,
        loss=MAE(),
        config=config,
        backend="optuna",
        num_samples=1,
    )
    df = _tiny_panel()
    nf = NeuralForecast(models=[auto_model], freq=1)
    nf.fit(df=df, val_size=8)
    return {"auto_model": auto_model, "nf": nf}


def test_neuralforecast_deep_copies_models_on_construction(
    fitted_auto_dlinear: dict[str, Any],
) -> None:
    auto_model = fitted_auto_dlinear["auto_model"]
    nf = fitted_auto_dlinear["nf"]
    assert nf.models[0] is not auto_model


def test_require_single_fitted_model_returns_fitted_object_not_original(
    fitted_auto_dlinear: dict[str, Any],
) -> None:
    auto_model = fitted_auto_dlinear["auto_model"]
    nf = fitted_auto_dlinear["nf"]

    fitted = _require_single_fitted_model(nf)

    assert fitted is nf.models[0]
    assert fitted is not auto_model
    # The pre-construction reference was never fit: neuralforecast's AutoModel
    # only sets `.model` once BaseAuto's search assigns the winning trial's
    # trained model onto the instance NeuralForecast actually holds.
    assert getattr(auto_model, "model", None) is None
    assert getattr(fitted, "model", None) is not None


def test_save_best_model_bundle_fails_on_original_but_passes_on_fitted(
    fitted_auto_dlinear: dict[str, Any], tmp_path: Any
) -> None:
    auto_model = fitted_auto_dlinear["auto_model"]
    nf = fitted_auto_dlinear["nf"]
    fitted = _require_single_fitted_model(nf)
    df = _tiny_panel()
    prediction = nf.predict()

    common_kwargs = dict(
        nf=nf,
        target=tmp_path / "bundle",
        train_panel=df,
        prediction_before=prediction,
        requested_config={},
        effective_config={},
        base_auto_args={},
        neuralforecast_args={},
        fit_args={},
        runtime={},
        gpu_pid={},
        save_dataset=False,
        atomic=True,
    )

    # Using the stale pre-construction reference must fail exactly as it did
    # before Fix 1 -- this is the bug the fix addresses, reproduced here
    # rather than asserted from memory.
    with pytest.raises(RuntimeError, match="AutoModel has no fitted .model"):
        save_best_model_bundle(auto_model=auto_model, **common_kwargs)

    # The fitted reference (`nf.models[0]`) must succeed, using a distinct
    # target directory since `atomic_directory` refuses to overwrite.
    common_kwargs["target"] = tmp_path / "bundle_fitted"
    manifest = save_best_model_bundle(auto_model=fitted, **common_kwargs)
    assert manifest["status"] == "PASS"


def test_require_single_fitted_model_raises_when_zero_models() -> None:
    fake_nf = SimpleNamespace(models=[])
    with pytest.raises(RuntimeError, match="Expected one fitted AutoModel, got 0"):
        _require_single_fitted_model(fake_nf)


def test_require_single_fitted_model_raises_when_multiple_models() -> None:
    fake_nf = SimpleNamespace(models=[object(), object()])
    with pytest.raises(RuntimeError, match="Expected one fitted AutoModel, got 2"):
        _require_single_fitted_model(fake_nf)


def test_require_single_fitted_model_accepts_exactly_one() -> None:
    sentinel = object()
    fake_nf = SimpleNamespace(models=[sentinel])
    assert _require_single_fitted_model(fake_nf) is sentinel
