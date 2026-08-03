from __future__ import annotations

from collections.abc import Callable
from typing import Any


def common_config(
    trial: Any,
    futr_exog_list: list[str],
    hist_exog_list: list[str],
    stat_exog_list: list[str],
) -> dict:
    return {
        "input_size": trial.suggest_categorical(
            "input_size",
            [14, 28, 56, 84, 112],
        ),
        "learning_rate": trial.suggest_float(
            "learning_rate",
            1e-4,
            1e-2,
            log=True,
        ),
        "max_steps": trial.suggest_categorical(
            "max_steps",
            [100, 200, 500, 1000],
        ),
        "batch_size": trial.suggest_categorical(
            "batch_size",
            [16, 32, 64],
        ),
        "windows_batch_size": trial.suggest_categorical(
            "windows_batch_size",
            [128, 256, 512, 1024],
        ),
        "scaler_type": trial.suggest_categorical(
            "scaler_type",
            ["identity", "standard", "robust"],
        ),
        "val_check_steps": trial.suggest_categorical(
            "val_check_steps",
            [25, 50, 100],
        ),
        "early_stop_patience_steps": trial.suggest_categorical(
            "early_stop_patience_steps",
            [-1, 3, 5, 10],
        ),
        "start_padding_enabled": trial.suggest_categorical(
            "start_padding_enabled",
            [False, True],
        ),
        "random_seed": trial.suggest_int(
            "random_seed",
            1,
            10000,
        ),
        "futr_exog_list": futr_exog_list,
        "hist_exog_list": hist_exog_list,
        "stat_exog_list": stat_exog_list,
    }


def tide_config(
    h: int,
    futr: list[str],
    hist: list[str],
    stat: list[str],
) -> Callable:
    def config(trial):
        result = common_config(
            trial,
            futr,
            hist,
            stat,
        )

        result.update(
            {
                "hidden_size": trial.suggest_categorical(
                    "hidden_size",
                    [64, 128, 256, 512],
                ),
                "decoder_output_dim": trial.suggest_categorical(
                    "decoder_output_dim",
                    [8, 16, 32, 64],
                ),
                "temporal_decoder_dim": trial.suggest_categorical(
                    "temporal_decoder_dim",
                    [16, 32, 64, 128],
                ),
                "dropout": trial.suggest_float(
                    "dropout",
                    0.0,
                    0.4,
                ),
                "layernorm": trial.suggest_categorical(
                    "layernorm",
                    [False, True],
                ),
                "num_encoder_layers": trial.suggest_int(
                    "num_encoder_layers",
                    1,
                    3,
                ),
                "num_decoder_layers": trial.suggest_int(
                    "num_decoder_layers",
                    1,
                    3,
                ),
            }
        )
        return result

    return config


def tft_config(
    h: int,
    futr: list[str],
    hist: list[str],
    stat: list[str],
) -> Callable:
    def config(trial):
        result = common_config(
            trial,
            futr,
            hist,
            stat,
        )

        result.update(
            {
                "hidden_size": trial.suggest_categorical(
                    "hidden_size",
                    [32, 64, 128, 256],
                ),
                "n_head": trial.suggest_categorical(
                    "n_head",
                    [1, 2, 4, 8],
                ),
                "attn_dropout": trial.suggest_float(
                    "attn_dropout",
                    0.0,
                    0.3,
                ),
                "dropout": trial.suggest_float(
                    "dropout",
                    0.0,
                    0.4,
                ),
                "grn_activation": trial.suggest_categorical(
                    "grn_activation",
                    ["ELU", "ReLU"],
                ),
                "n_rnn_layers": trial.suggest_int(
                    "n_rnn_layers",
                    1,
                    2,
                ),
                "rnn_type": trial.suggest_categorical(
                    "rnn_type",
                    ["lstm", "gru"],
                ),
                "one_rnn_initial_state": trial.suggest_categorical(
                    "one_rnn_initial_state",
                    [False, True],
                ),
            }
        )
        return result

    return config


def recurrent_config(
    h: int,
    futr: list[str],
    hist: list[str],
    stat: list[str],
) -> Callable:
    def config(trial):
        result = common_config(
            trial,
            futr,
            hist,
            stat,
        )

        result.update(
            {
                "encoder_hidden_size": trial.suggest_categorical(
                    "encoder_hidden_size",
                    [32, 64, 128, 256],
                ),
                "encoder_n_layers": trial.suggest_int(
                    "encoder_n_layers",
                    1,
                    3,
                ),
                "encoder_dropout": trial.suggest_float(
                    "encoder_dropout",
                    0.0,
                    0.4,
                ),
                "decoder_hidden_size": trial.suggest_categorical(
                    "decoder_hidden_size",
                    [32, 64, 128, 256],
                ),
                "decoder_layers": trial.suggest_int(
                    "decoder_layers",
                    1,
                    3,
                ),
                "context_size": trial.suggest_categorical(
                    "context_size",
                    [5, 10, 20, 50],
                ),
            }
        )
        return result

    return config
