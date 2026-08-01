from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import yaml
import neuralforecast.auto as auto_module
import neuralforecast.models as model_module
from neuralforecast.common._base_auto import BaseAuto


CLASSIFICATION = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_model_classification_v2.json"
)

MATRIX = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_model_matrix_v2.json"
)

LOSSES = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_loss_classification_v2.json"
)

OUTPUT = Path(
    "configs/generated/"
    "neuralforecast_complete_search_spec.yaml"
)


SPECIAL_NAME_MAP = {
    "AutoAutoformer": "Autoformer",
    "AutoiTransformer": "iTransformer",
}


FORBIDDEN_FEATURES = [
    "hist_diff_1",
    "hist_diff_7",
]


POINT_LOSS_CONFIGS = [
    {
        "name": "MAE",
        "kwargs": {},
        "enabled": True,
    },
    {
        "name": "MSE",
        "kwargs": {},
        "enabled": True,
    },
    {
        "name": "RMSE",
        "kwargs": {},
        "enabled": True,
    },
    {
        "name": "HuberLoss",
        "kwargs": {
            "delta": [0.5, 1.0, 2.0],
        },
        "enabled": True,
    },
    {
        "name": "TukeyLoss",
        "kwargs": {
            "c": [2.0, 4.685, 8.0],
        },
        "enabled": True,
    },
    {
        "name": "MAPE",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Potential instability for small target values"
        ),
    },
    {
        "name": "SMAPE",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Enable only after zero/small-value audit"
        ),
    },
    {
        "name": "MASE",
        "kwargs": {
            "seasonality": [1, 7, 14],
        },
        "enabled": False,
        "reason": (
            "Requires justified seasonality"
        ),
    },
    {
        "name": "relMSE",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Requires benchmark semantics audit"
        ),
    },
]


PROBABILISTIC_LOSS_CONFIGS = [
    {
        "name": "MQLoss",
        "kwargs": {
            "level": [
                [50],
                [80],
                [80, 90],
                [50, 80, 90],
            ],
        },
        "enabled": True,
    },
    {
        "name": "DistributionLoss",
        "kwargs": {
            "distribution": [
                "Normal",
                "StudentT",
            ],
            "level": [
                [80],
                [80, 90],
            ],
        },
        "enabled": True,
    },
    {
        "name": "GMM",
        "kwargs": {
            "n_components": [1, 2, 3, 5],
            "level": [
                [80],
                [80, 90],
            ],
        },
        "enabled": True,
    },
    {
        "name": "NBMM",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Count-distribution suitability must be audited"
        ),
    },
    {
        "name": "PMM",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Count-distribution suitability must be audited"
        ),
    },
    {
        "name": "Tweedie",
        "kwargs": {},
        "enabled": False,
        "reason": (
            "Direct construction semantics require audit"
        ),
    },
]


COMMON_MODEL_GRID = {
    "input_size": [7, 14, 28, 56, 84, 112, 168],
    "learning_rate": [
        0.00003,
        0.0001,
        0.0003,
        0.001,
        0.003,
        0.01,
    ],
    "max_steps": [50, 100, 200, 500, 1000],
    "batch_size": [8, 16, 32, 64, 128],
    "valid_batch_size": [None, 16, 32, 64],
    "windows_batch_size": [
        64,
        128,
        256,
        512,
        1024,
    ],
    "inference_windows_batch_size": [
        64,
        128,
        256,
        512,
        1024,
    ],
    "scaler_type": [
        "identity",
        "standard",
        "robust",
    ],
    "num_lr_decays": [-1, 1, 2, 3],
    "early_stop_patience_steps": [
        -1,
        3,
        5,
        10,
        20,
    ],
    "val_check_steps": [10, 25, 50, 100],
    "start_padding_enabled": [False, True],
    "training_data_availability_threshold": [
        0.0,
        0.5,
        0.8,
        1.0,
    ],
    "step_size": [1],
    "drop_last_loader": [False, True],
    "random_seed": [42, 123, 2026],
}


AUTO_WRAPPER_GRID = {
    "backend": [
        "optuna",
        "ray",
    ],
    "num_samples": [
        20,
        50,
        100,
        200,
    ],
    "time_budget": [
        None,
        1800,
        3600,
    ],
    "refit_with_val": [
        False,
        True,
    ],
    "verbose": [
        True,
    ],
    "optuna_sampler": [
        "RandomSampler",
        "TPESampler",
        "QMCSampler",
        "CmaEsSampler",
    ],
    "ray_scheduler": [
        "FIFOScheduler",
        "ASHAScheduler",
        "HyperBandScheduler",
        "MedianStoppingRule",
    ],
}


CORE_GRID = {
    "local_scaler_type": [
        None,
        "standard",
        "robust",
        "minmax",
    ],
    "local_static_scaler_type": [
        None,
        "standard",
        "robust",
    ],
}


FIT_GRID = {
    "val_size": [5, 10, 20, 30, 50],
    "use_init_models": [False],
}


CV_GRID = {
    "n_windows": [5, 10, 20, 50],
    "step_size": [1],
    "refit": [False, 1, 5, 10],
    "use_init_models": [False, True],
}


TRAINER_GRID = {
    "precision": [
        "32-true",
        "16-mixed",
        "bf16-mixed",
    ],
    "gradient_clip_val": [
        0.0,
        0.5,
        1.0,
        5.0,
    ],
    "gradient_clip_algorithm": [
        "norm",
        "value",
    ],
    "accumulate_grad_batches": [
        1,
        2,
        4,
    ],
    "deterministic": [
        True,
        False,
    ],
    "benchmark": [
        False,
        True,
    ],
}


EXOG_GROUPS = {
    "calendar_raw": {
        "type": "future",
        "columns": [
            "feat_year",
            "feat_month",
            "feat_day",
            "feat_dayofweek",
            "feat_weekofyear",
            "feat_dayofyear",
        ],
    },
    "calendar_flags": {
        "type": "future",
        "columns": [
            "feat_is_weekend",
            "feat_is_month_start",
            "feat_is_month_end",
        ],
    },
    "calendar_cyclical": {
        "type": "future",
        "columns": [
            "feat_dow_sin",
            "feat_dow_cos",
            "feat_month_sin",
            "feat_month_cos",
        ],
    },
    "lags_short": {
        "type": "historical",
        "columns": [
            "hist_lag_1",
            "hist_lag_2",
            "hist_lag_3",
            "hist_lag_7",
        ],
    },
    "lags_long": {
        "type": "historical",
        "columns": [
            "hist_lag_14",
            "hist_lag_28",
        ],
    },
    "rolling_mean": {
        "type": "historical",
        "columns": [
            "hist_roll_mean_3",
            "hist_roll_mean_7",
            "hist_roll_mean_14",
            "hist_roll_mean_28",
        ],
    },
    "rolling_std": {
        "type": "historical",
        "columns": [
            "hist_roll_std_7",
            "hist_roll_std_14",
            "hist_roll_std_28",
        ],
    },
    "rolling_range": {
        "type": "historical",
        "columns": [
            "hist_roll_min_7",
            "hist_roll_max_7",
            "hist_roll_min_14",
            "hist_roll_max_14",
        ],
    },
    "ewm": {
        "type": "historical",
        "columns": [
            "hist_ewm_mean_7",
            "hist_ewm_mean_14",
        ],
    },
}


classification = json.loads(
    CLASSIFICATION.read_text(encoding="utf-8")
)

matrix = json.loads(
    MATRIX.read_text(encoding="utf-8")
)

losses = json.loads(
    LOSSES.read_text(encoding="utf-8")
)

matrix_by_auto = {
    record["auto_model"]: record
    for record in matrix
}

eligible_models = [
    record
    for record in classification["records"]
    if record["eligible_current_policy"]
]

models: dict[str, Any] = {}

for record in eligible_models:
    auto_name = record["auto_model"]
    matrix_record = matrix_by_auto[auto_name]

    base_name = matrix_record["base_model"]
    model_cls = getattr(model_module, base_name)

    signature = inspect.signature(model_cls.__init__)

    parameters = set(signature.parameters) - {"self"}

    model_grid = {
        key: value
        for key, value in COMMON_MODEL_GRID.items()
        if key in parameters
    }

    models[auto_name] = {
        "base_model": base_name,
        "enabled": True,
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "required_parameters": (
            matrix_record["required_parameters"]
        ),
        "supports": {
            "future_exog": (
                matrix_record["future_exog"]
            ),
            "historical_exog": (
                matrix_record["historical_exog"]
            ),
            "static_exog": (
                matrix_record["static_exog"]
            ),
            "categorical_exog": (
                matrix_record["categorical_exog"]
            ),
        },
        "common_parameter_grid": model_grid,
        "model_specific_parameters": sorted(
            parameters
            - set(COMMON_MODEL_GRID)
            - {
                "h",
                "loss",
                "valid_loss",
                "futr_exog_list",
                "hist_exog_list",
                "stat_exog_list",
                "cat_exog_list",
                "categorical_cardinalities",
                "cat_emb_dim",
                "optimizer",
                "optimizer_kwargs",
                "lr_scheduler",
                "lr_scheduler_kwargs",
                "dataloader_kwargs",
                "alias",
                "trainer_kwargs",
            }
        ),
        "signature": matrix_record["model_signature"],
    }

payload = {
    "metadata": {
        "neuralforecast_version": "3.2.0",
        "game": "loto7",
        "horizon": 1,
        "generated_from_runtime_introspection": True,
        "eligible_auto_models": len(models),
    },
    "policy": {
        "univariate_only": True,
        "forbidden_features": FORBIDDEN_FEATURES,
        "primary_metric": "macro_mae",
        "secondary_metrics": [
            "macro_mse",
            "macro_within_1",
            "all_positions_within_1",
            "positive_fold_rate",
            "training_seconds",
        ],
    },
    "search_methods": [
        "manual_coarse_grid",
        "auto_default_optuna",
        "auto_custom_optuna",
        "auto_default_ray",
        "auto_custom_ray",
        "manual_fine_grid",
    ],
    "training_modes": [
        "separate",
        "global",
        "global_position",
    ],
    "auto_wrapper_grid": AUTO_WRAPPER_GRID,
    "core_grid": CORE_GRID,
    "fit_grid": FIT_GRID,
    "cross_validation_grid": CV_GRID,
    "trainer_grid": TRAINER_GRID,
    "point_loss_grid": POINT_LOSS_CONFIGS,
    "probabilistic_loss_grid": (
        PROBABILISTIC_LOSS_CONFIGS
    ),
    "exogenous_groups": EXOG_GROUPS,
    "models": models,
}

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
    ),
    encoding="utf-8",
)

print("eligible_auto_models=", len(models))
print("search_methods=", len(payload["search_methods"]))
print("point_losses=", len(POINT_LOSS_CONFIGS))
print(
    "probabilistic_losses=",
    len(PROBABILISTIC_LOSS_CONFIGS),
)
print("exog_groups=", len(EXOG_GROUPS))
print("OUT=", OUTPUT)
print("NF_COMPLETE_SEARCH_SPEC=PASS")
