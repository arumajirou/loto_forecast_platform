import pandas as pd

from src.ml import model_runner as mr


def test_build_param_grid_defaults_mode():
    grid = mr._build_param_grid(user_spec=None, mode="defaults")
    # 1 通りだけであること
    assert isinstance(grid, list)
    assert len(grid) == 1
    params = grid[0]
    # デフォルトキーが含まれていること
    assert "loss" in params
    assert "h" in params
    assert "freq" in params


def test_build_param_grid_grid_mode():
    spec = {
        "loss": ["mse", "mae"],
        "h": [14, 28],
    }
    grid = mr._build_param_grid(user_spec=spec, mode="grid")
    # 2 x 2 = 4 通り
    assert len(grid) == 4
    combos = {(p["loss"], p["h"]) for p in grid}
    assert combos == {("mse", 14), ("mse", 28), ("mae", 14), ("mae", 28)}


class DummyNF:
    def __init__(self, model, freq, local_scaler_type=None):
        self.model = model
        self.freq = freq
        self.local_scaler_type = local_scaler_type
        self.fit_called = False

    def fit(self, df, futr_exog_list=None, hist_exog_list=None, stat_exog_list=None, verbose=False):
        # fit が呼ばれたことだけ確認
        self.fit_called = True
        # futr/hist/stat が list か None であることを確認
        assert (futr_exog_list is None) or isinstance(futr_exog_list, list)
        assert (hist_exog_list is None) or isinstance(hist_exog_list, list)
        assert (stat_exog_list is None) or isinstance(stat_exog_list, list)

    def predict(self):
        # シンプルな DataFrame を返す
        return pd.DataFrame(
            {
                "unique_id": ["N1", "N1", "N2"],
                "ds": pd.date_range("2020-01-01", periods=3),
                "AutoModel": [0.1, 0.2, 0.3],
            }
        )

    def save(self, path):
        import os
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "dummy.txt"), "w", encoding="utf-8") as f:
            f.write("ok")


def test_run_loto_experiment_happy_path(monkeypatch, tmp_path):
    # load_panel_by_loto をダミー化
    panel_df = pd.DataFrame(
        {
            "unique_id": ["N1", "N1", "N2"],
            "ds": pd.date_range("2020-01-01", periods=3),
            "y": [1.0, 2.0, 3.0],
            "hist_x": [0.1, 0.2, 0.3],
            "stat_s": [1, 1, 2],
            "futr_f": [10, 11, 12],
        }
    )

    monkeypatch.setattr(mr, "load_panel_by_loto", lambda table_name, loto, unique_ids: panel_df)

    # AutoModel / NeuralForecast / ロガー / リソース計測をダミー化
    monkeypatch.setattr(mr, "build_auto_model", lambda **kwargs: object())
    monkeypatch.setattr(mr, "build_neuralforecast", lambda model, freq, local_scaler_type=None: DummyNF(model, freq, local_scaler_type))
    monkeypatch.setattr(mr, "collect_resource_snapshot", lambda: {"cpu": 10})

    # log_run_start は run_id=1 を返すだけ
    monkeypatch.setattr(
        mr,
        "log_run_start",
        lambda **kwargs: 1,
    )
    # log_run_end / log_run_error は何もしないダミー
    monkeypatch.setattr(mr, "log_run_end", lambda **kwargs: None)
    monkeypatch.setattr(mr, "log_run_error", lambda run_id, exc: None)

    preds, meta = mr.run_loto_experiment(
        table_name="nf_loto_final",
        loto="bingo5",
        unique_ids=["N1", "N2"],
        model_name="AutoTFT",
        backend="optuna",
        horizon=2,
        loss="mse",
        metric="val_loss",
        num_samples=1,
        freq="D",
        local_scaler_type="robust",
        val_size=2,
        refit_with_val=True,
        use_init_models=False,
        early_stop=True,
        early_stop_patience_steps=3,
    )

    assert not preds.empty
    assert meta["run_id"] == 1
    assert meta["model_name"] == "AutoTFT"
    assert meta["backend"] == "optuna"
    assert meta["horizon"] == 2


def test_sweep_loto_experiments_uses_param_grid(monkeypatch):
    # run_loto_experiment をダミー化して、呼ばれた回数をカウント
    calls = []

    def fake_run(**kwargs):
        import pandas as pd

        calls.append(kwargs)
        # preds/meta のダミー
        preds = pd.DataFrame({"y_hat": [1.0, 2.0]})
        meta = {
            "run_id": len(calls),
            "model_name": kwargs["model_name"],
            "backend": kwargs["backend"],
            "horizon": kwargs["horizon"],
            "loss": kwargs["loss"],
        }
        return preds, meta

    monkeypatch.setattr(mr, "run_loto_experiment", fake_run)

    param_spec = {
        "loss": ["mse", "mae"],
        "h": [14, 28],
        "freq": ["D"],
        "local_scaler_type": ["robust"],
        "val_size": [28],
        "refit_with_val": [True],
        "use_init_models": [False],
        "early_stop": [True],
        "early_stop_patience_steps": [3],
    }

    results = mr.sweep_loto_experiments(
        table_name="nf_loto_final",
        loto="bingo5",
        unique_ids=["N1", "N2"],
        model_names=["AutoTFT"],
        backends=["optuna"],
        param_spec=param_spec,
        mode="grid",
        num_samples=1,
        cpus=1,
        gpus=0,
    )

    # loss(2) x h(2) x model(1) x backend(1) = 4 通り
    assert len(results) == 4
    assert len(calls) == 4
    # すべて run_id がユニークであること
    assert {r.meta["run_id"] for r in results} == {1, 2, 3, 4}
