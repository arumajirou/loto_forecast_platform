from __future__ import annotations

import optuna

from neuralforecast.auto import (
    AutoTiDE,
    AutoTFT,
    AutoGRU,
    AutoLSTM,
    AutoTCN,
    AutoNBEATSx,
    AutoNHITS,
)
from neuralforecast.losses.pytorch import MAE

from loto.auto_search_spaces import (
    tide_config,
    tft_config,
    recurrent_config,
)


def build_auto_model(
    model_name: str,
    h: int,
    futr: list[str],
    hist: list[str],
    stat: list[str],
    num_samples: int,
    seed: int,
):
    sampler = optuna.samplers.TPESampler(
        seed=seed,
    )

    common = {
        "h": h,
        "loss": MAE(),
        "valid_loss": MAE(),
        "backend": "optuna",
        "num_samples": num_samples,
        "search_alg": sampler,
        "refit_with_val": True,
        "verbose": True,
    }

    if model_name == "AutoTiDE":
        return AutoTiDE(
            config=tide_config(
                h,
                futr,
                hist,
                stat,
            ),
            **common,
        )

    if model_name == "AutoTFT":
        return AutoTFT(
            config=tft_config(
                h,
                futr,
                hist,
                stat,
            ),
            **common,
        )

    if model_name == "AutoGRU":
        return AutoGRU(
            config=recurrent_config(
                h,
                futr,
                hist,
                stat,
            ),
            **common,
        )

    if model_name == "AutoLSTM":
        return AutoLSTM(
            config=recurrent_config(
                h,
                futr,
                hist,
                stat,
            ),
            **common,
        )

    # 最初は公式デフォルト探索空間を使用
    auto_classes = {
        "AutoTCN": AutoTCN,
        "AutoNBEATSx": AutoNBEATSx,
        "AutoNHITS": AutoNHITS,
    }

    cls = auto_classes.get(model_name)

    if cls is None:
        raise ValueError(f"Unsupported auto model: {model_name}")

    default_config = cls.get_default_config(
        h=h,
        backend="optuna",
    )

    def config_with_exog(trial):
        config = dict(default_config(trial))
        config["futr_exog_list"] = list(futr)
        config["hist_exog_list"] = list(hist)
        config["stat_exog_list"] = list(stat)
        return config

    return cls(
        config=config_with_exog,
        **common,
    )
