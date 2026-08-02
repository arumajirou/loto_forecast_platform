import pytest

from src.ml import automodel_builder as ab


def test_split_exog_columns():
    cols = ["unique_id", "ds", "y", "hist_x1", "stat_cat", "futr_holiday"]
    exogs = ab.split_exog_columns(cols)
    assert "hist_x1" in exogs.hist_exog
    assert "stat_cat" in exogs.stat_exog
    assert "futr_holiday" in exogs.futr_exog


def test_get_loss_instance_known_losses():
    for name in ["mse", "mae", "smape"]:
        loss = ab.get_loss_instance(name)
        # 損失オブジェクトであることだけ確認
        assert callable(loss)


def test_get_loss_instance_unknown_raises():
    with pytest.raises(ValueError):
        ab.get_loss_instance("unknown_loss")


def test_resolve_early_stop_config():
    cfg_true = ab._resolve_early_stop_config(True, patience=5)
    assert cfg_true.get("early_stop_patience_steps") == 5

    cfg_false = ab._resolve_early_stop_config(False, patience=5)
    assert cfg_false.get("early_stop_patience_steps") == -1

    cfg_none = ab._resolve_early_stop_config(None, patience=5)
    # None の場合はキーが無い
    assert "early_stop_patience_steps" not in cfg_none


class DummyModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class DummyNF:
    def __init__(self, models, freq, local_scaler_type=None):
        self.models = models
        self.freq = freq
        self.local_scaler_type = local_scaler_type


def test_build_auto_model_uses_common_kwargs(monkeypatch):
    # AutoTFT をダミーに差し替え
    monkeypatch.setattr(ab, "AutoTFT", DummyModel)

    model = ab.build_auto_model(
        model_name="AutoTFT",
        backend="optuna",
        h=24,
        loss_name="mse",
        num_samples=3,
        search_space=None,
        early_stop=True,
        early_stop_patience_steps=7,
        verbose=True,
    )

    assert isinstance(model, DummyModel)
    k = model.kwargs
    assert k["h"] == 24
    assert k["backend"] == "optuna"
    assert k["num_samples"] == 3
    assert k["early_stop_patience_steps"] == 7
    # loss と valid_loss が同一インスタンスであること
    assert k["loss"] is k["valid_loss"]


def test_build_auto_model_rejects_unknown_backend():
    with pytest.raises(ValueError):
        ab.build_auto_model(
            model_name="AutoTFT",
            backend="invalid_backend",
            h=24,
            loss_name="mse",
            num_samples=3,
        )


def test_build_neuralforecast_wraps_model(monkeypatch):
    # NeuralForecast をダミーに
    monkeypatch.setattr(ab, "NeuralForecast", DummyNF)

    dummy_model = DummyModel()
    nf = ab.build_neuralforecast(
        model=dummy_model,
        freq="D",
        local_scaler_type="robust",
    )
    assert isinstance(nf, DummyNF)
    assert nf.freq == "D"
    assert nf.local_scaler_type == "robust"
