from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


SPACE_SOURCE = Path(
    "configs/generated/"
    "neuralforecast_normalized_fixed_seed_spaces.json"
)

SEARCH_SPEC_SOURCE = Path(
    "configs/generated/"
    "neuralforecast_complete_search_spec.yaml"
)

OUTPUT_DIR = Path(
    "configs/generated/neuralforecast_profiles"
)


space = json.loads(
    SPACE_SOURCE.read_text(encoding="utf-8")
)

search_spec = yaml.safe_load(
    SEARCH_SPEC_SOURCE.read_text(encoding="utf-8")
)

all_models = sorted(space["models"])

expected_models = {
    "AutoAutoformer",
    "AutoBiTCN",
    "AutoDLinear",
    "AutoDeepAR",
    "AutoDeepNPTS",
    "AutoDilatedRNN",
    "AutoFEDformer",
    "AutoGRU",
    "AutoInformer",
    "AutoKAN",
    "AutoLSTM",
    "AutoMLP",
    "AutoNBEATS",
    "AutoNBEATSx",
    "AutoNHITS",
    "AutoNLinear",
    "AutoPatchTST",
    "AutoRNN",
    "AutoTCN",
    "AutoTFT",
    "AutoTiDE",
    "AutoTimesNet",
    "AutoVanillaTransformer",
    "AutoxLSTM",
}

if set(all_models) != expected_models:
    raise ValueError(
        "Unexpected eligible Auto model set: "
        f"missing={sorted(expected_models - set(all_models))}, "
        f"extra={sorted(set(all_models) - expected_models)}"
    )


COMMON_POLICY: dict[str, Any] = {
    "game": "loto7",
    "horizon": 1,
    "univariate_only": True,
    "primary_metric": "macro_mae",
    "secondary_metrics": [
        "macro_mse",
        "macro_within_1",
        "all_positions_within_1",
        "positive_fold_rate",
        "training_seconds",
        "peak_vram_mib",
    ],
    "forbidden_features": [
        "hist_diff_1",
        "hist_diff_7",
    ],
    "search_seed": 42,
    "formal_evaluation_seeds": [
        42,
        123,
        2026,
    ],
    "fail_on_nonfinite_prediction": True,
    "fail_on_cpu_fallback": True,
    "require_cuda_evidence": True,
    "require_prediction_shape_check": True,
    "require_temporal_leakage_check": True,
}


profiles: dict[str, dict[str, Any]] = {
    "smoke": {
        "description": (
            "Minimal runtime and compatibility certification"
        ),
        "models": [
            "AutoDLinear",
            "AutoGRU",
            "AutoNHITS",
            "AutoTFT",
            "AutoTiDE",
            "AutoPatchTST",
        ],
        "backends": [
            "optuna",
        ],
        "search_space": "normalized_fixed_seed",
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "losses": [
            {
                "name": "MAE",
                "kwargs": {},
            },
        ],
        "exog_conditions": [
            "no_exog",
            "calendar_cyclical",
        ],
        "num_samples": 1,
        "outer_windows": 2,
        "inner_windows": 1,
        "max_steps_override": 5,
        "val_size": 5,
        "precision": "32-true",
        "deterministic": True,
        "benchmark": False,
        "stop_on_first_error": False,
    },
    "screening": {
        "description": (
            "All-model low-cost screening"
        ),
        "models": all_models,
        "backends": [
            "optuna",
        ],
        "search_space": "normalized_fixed_seed",
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "losses": [
            {
                "name": "MAE",
                "kwargs": {},
            },
            {
                "name": "HuberLoss",
                "kwargs": {
                    "delta": 1.0,
                },
            },
        ],
        "exog_conditions": [
            "no_exog",
            "calendar_cyclical",
            "lags_short",
            "rolling_mean",
            "all_safe_exog",
        ],
        "num_samples": 5,
        "outer_windows": 5,
        "inner_windows": 3,
        "max_steps_cap": 200,
        "val_size": 10,
        "precision": "32-true",
        "deterministic": True,
        "benchmark": False,
        "promotion": {
            "top_k_models": 8,
            "minimum_success_rate": 0.8,
            "maximum_nonfinite_predictions": 0,
        },
    },
    "broad": {
        "description": (
            "Broader search for screening winners"
        ),
        "models_from": (
            "screening.promotion.top_k_models"
        ),
        "backends": [
            "optuna",
            "ray",
        ],
        "search_spaces": [
            "official_optuna",
            "official_ray",
            "normalized_fixed_seed",
        ],
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "losses": [
            {
                "name": "MAE",
                "kwargs": {},
            },
            {
                "name": "MSE",
                "kwargs": {},
            },
            {
                "name": "HuberLoss",
                "kwargs": {
                    "delta": 1.0,
                },
            },
            {
                "name": "TukeyLoss",
                "kwargs": {
                    "c": 4.685,
                },
            },
        ],
        "num_samples": 30,
        "outer_windows": 10,
        "inner_windows": 5,
        "max_steps_cap": 500,
        "val_size": 20,
        "precision": "32-true",
        "deterministic": True,
        "benchmark": False,
        "promotion": {
            "top_k_configurations": 12,
            "top_k_models": 4,
        },
    },
    "fine": {
        "description": (
            "Model-specific fine search around broad winners"
        ),
        "configurations_from": (
            "broad.promotion.top_k_configurations"
        ),
        "models_from": (
            "broad.promotion.top_k_models"
        ),
        "backends": [
            "optuna",
        ],
        "search_spaces": [
            "normalized_fixed_seed",
            "custom_extended",
        ],
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "losses": [
            {
                "name": "MAE",
                "kwargs": {},
            },
            {
                "name": "MSE",
                "kwargs": {},
            },
            {
                "name": "HuberLoss",
                "kwargs_grid": {
                    "delta": [
                        0.5,
                        1.0,
                        2.0,
                    ],
                },
            },
            {
                "name": "TukeyLoss",
                "kwargs_grid": {
                    "c": [
                        2.0,
                        4.685,
                        8.0,
                    ],
                },
            },
        ],
        "num_samples": 100,
        "outer_windows": 20,
        "inner_windows": 10,
        "max_steps_cap": 1500,
        "val_size": 30,
        "precision": "32-true",
        "deterministic": True,
        "benchmark": False,
        "promotion": {
            "top_k_configurations": 5,
        },
    },
    "formal": {
        "description": (
            "Strict frozen-configuration outer evaluation"
        ),
        "configurations_from": (
            "fine.promotion.top_k_configurations"
        ),
        "search_enabled": False,
        "retune_inside_outer_fold": False,
        "configuration_frozen_before_test": True,
        "training_modes": [
            "separate",
            "global",
            "global_position",
        ],
        "evaluation_seeds": [
            42,
            123,
            2026,
        ],
        "outer_windows": 50,
        "step_size": 1,
        "refit": 1,
        "precision": "32-true",
        "deterministic": True,
        "benchmark": False,
        "save_predictions": True,
        "save_checkpoints": True,
        "save_fold_metrics": True,
        "save_gpu_evidence": True,
        "save_environment_lock": True,
        "require_complete_fold_set": True,
    },
}


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

manifest: dict[str, Any] = {
    "metadata": {
        "neuralforecast_version": (
            space["metadata"]["neuralforecast_version"]
        ),
        "model_count": len(all_models),
        "profile_count": len(profiles),
        "space_source": str(SPACE_SOURCE),
        "search_spec_source": str(
            SEARCH_SPEC_SOURCE
        ),
    },
    "profiles": {},
}

for name, profile in profiles.items():
    payload = {
        "metadata": {
            "profile": name,
            "neuralforecast_version": (
                space["metadata"][
                    "neuralforecast_version"
                ]
            ),
        },
        "policy": COMMON_POLICY,
        "profile": profile,
    }

    output = OUTPUT_DIR / f"{name}.yaml"

    output.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    manifest["profiles"][name] = {
        "path": str(output),
        "description": profile["description"],
    }

manifest_path = OUTPUT_DIR / "manifest.yaml"

manifest_path.write_text(
    yaml.safe_dump(
        manifest,
        sort_keys=False,
        allow_unicode=True,
    ),
    encoding="utf-8",
)

print("models=", len(all_models))
print("profiles=", len(profiles))

for name in profiles:
    print(
        name,
        "->",
        OUTPUT_DIR / f"{name}.yaml",
    )

print("manifest=", manifest_path)
print("NF_RESEARCH_PROFILES=PASS")
