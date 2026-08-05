from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .contracts import CoverageStatus


@dataclass(frozen=True)
class ArgumentCoverage:
    layer: str
    argument: str
    primary_value: Any
    alternate_values: tuple[Any, ...]
    status: CoverageStatus
    note: str


BASE_AUTO_ARGUMENTS = (
    "cls_model",
    "h",
    "loss",
    "valid_loss",
    "config",
    "search_alg",
    "num_samples",
    "time_budget",
    "refit_with_val",
    "verbose",
    "alias",
    "backend",
    "callbacks",
    "ray_options",
    "optuna_options",
    "cpus",
    "gpus",
)

NEURALFORECAST_ARGUMENTS = (
    "models",
    "freq",
    "local_scaler_type",
    "local_static_scaler_type",
)

FIT_ARGUMENTS = (
    "df",
    "static_df",
    "val_size",
    "val_df",
    "use_init_models",
    "verbose",
    "id_col",
    "time_col",
    "target_col",
    "distributed_config",
    "prediction_intervals",
)


def build_argument_catalog() -> list[dict[str, Any]]:
    rows: list[ArgumentCoverage] = [
        ArgumentCoverage(
            "BaseAuto",
            "cls_model",
            "runtime registry",
            (),
            CoverageStatus.PLANNED,
            "Every BaseAuto subclass is resolved to its wrapped model.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto", "h", 1, (5,), CoverageStatus.PLANNED, "h=5 is a separate ablation."
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "loss",
            "model default",
            ("MAE", "MSE", "distribution-compatible"),
            CoverageStatus.PLANNED,
            "Compatibility matrix controls alternates.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "valid_loss",
            "model default",
            ("MAE", "MSE"),
            CoverageStatus.PLANNED,
            "Hit@±1 is applied by an external validation replay.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "config",
            "official default_config",
            ("coverage fixed configs",),
            CoverageStatus.PLANNED,
            "Every key is catalogued and covered.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "search_alg",
            "BasicVariantGenerator(seed=1)",
            ("Optuna sampler",),
            CoverageStatus.PLANNED,
            "Ray and Optuna tracks are separate.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto", "num_samples", 10, (1, 30), CoverageStatus.PLANNED, "1=smoke; 30+=extended."
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "time_budget",
            None,
            ("bounded seconds",),
            CoverageStatus.PLANNED,
            "Bounded run is a contract track.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "refit_with_val",
            False,
            (True,),
            CoverageStatus.PLANNED,
            "Both branches are covered.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "verbose",
            False,
            (True,),
            CoverageStatus.PLANNED,
            "True is a contract track.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "alias",
            "explicit unique alias",
            (None,),
            CoverageStatus.PLANNED,
            "Alias is part of the artifact key.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "backend",
            "ray",
            ("optuna",),
            CoverageStatus.PLANNED,
            "All models get an Optuna contract smoke when supported.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "callbacks",
            "trial persistence callback/mixin",
            (None,),
            CoverageStatus.PLANNED,
            "No silent trial loss.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "ray_options",
            "RayOptions(cpus,gpus)",
            (None,),
            CoverageStatus.PLANNED,
            "NeuralForecast 3.2.0 resource path.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "optuna_options",
            "OptunaOptions",
            (None,),
            CoverageStatus.PLANNED,
            "Only applicable to Optuna.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "cpus",
            None,
            (),
            CoverageStatus.UNSUPPORTED_BY_VERSION,
            "NeuralForecast 3.2.0 rejects direct cpus; use RayOptions.",
        ),  # noqa: E501
        ArgumentCoverage(
            "BaseAuto",
            "gpus",
            None,
            (),
            CoverageStatus.UNSUPPORTED_BY_VERSION,
            "NeuralForecast 3.2.0 rejects direct gpus; use RayOptions.",
        ),  # noqa: E501
        ArgumentCoverage(
            "NeuralForecast",
            "models",
            "one AutoModel per formal task",
            ("multi-model smoke",),
            CoverageStatus.PLANNED,
            "All models in one NeuralForecast must share h.",
        ),  # noqa: E501
        ArgumentCoverage(
            "NeuralForecast",
            "freq",
            1,
            ("invalid-value rejection",),
            CoverageStatus.PLANNED,
            "MiniLoto draw index is an integer timeline.",
        ),  # noqa: E501
        ArgumentCoverage(
            "NeuralForecast",
            "local_scaler_type",
            None,
            ("standard", "robust", "robust-iqr", "minmax", "boxcox"),
            CoverageStatus.PLANNED,
            "Main comparison keeps None.",
        ),  # noqa: E501
        ArgumentCoverage(
            "NeuralForecast",
            "local_static_scaler_type",
            None,
            ("contract synthetic static data",),
            CoverageStatus.PLANNED,
            "Real data has no static covariates.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "df",
            "temporal training panel",
            (None,),
            CoverageStatus.PLANNED,
            "df=None is only used after a stored dataset is loaded.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "static_df",
            None,
            ("synthetic contract static data",),
            CoverageStatus.PLANNED,
            "Main MiniLoto data has no static_df.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "val_size",
            50,
            (0,),
            CoverageStatus.PLANNED,
            "val_size=0 is paired with explicit val_df.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "val_df",
            None,
            ("explicit validation frame",),
            CoverageStatus.PLANNED,
            "Never combine with non-zero val_size.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "use_init_models",
            False,
            (True,),
            CoverageStatus.PLANNED,
            "Reinitialization contract track.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit", "verbose", False, (True,), CoverageStatus.PLANNED, "True is a contract track."
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "id_col",
            "unique_id",
            ("series_id",),
            CoverageStatus.PLANNED,
            "Alternate names are contract-only.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "time_col",
            "ds",
            ("time_index",),
            CoverageStatus.PLANNED,
            "Alternate names are contract-only.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "target_col",
            "y",
            ("target",),
            CoverageStatus.PLANNED,
            "Alternate names are contract-only.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "distributed_config",
            None,
            ("Spark contract track",),
            CoverageStatus.PLANNED,
            "Overall status remains partial until Spark is executed.",
        ),  # noqa: E501
        ArgumentCoverage(
            "fit",
            "prediction_intervals",
            None,
            ("conformal track",),
            CoverageStatus.PLANNED,
            "Main point-forecast comparison keeps None.",
        ),  # noqa: E501
    ]
    return [asdict(row) for row in rows]


def runtime_signature_catalog() -> dict[str, Any]:
    import inspect

    from neuralforecast import NeuralForecast
    from neuralforecast.common._base_auto import BaseAuto

    targets = {
        "BaseAuto": (BaseAuto, BASE_AUTO_ARGUMENTS),
        "NeuralForecast": (NeuralForecast, NEURALFORECAST_ARGUMENTS),
        "fit": (NeuralForecast.fit, FIT_ARGUMENTS),
    }
    output: dict[str, Any] = {}
    for name, (target, expected) in targets.items():
        signature = inspect.signature(target)
        actual = [key for key in signature.parameters if key not in {"self", "cls"}]
        output[name] = {
            "signature": str(signature),
            "expected_arguments": list(expected),
            "actual_arguments": actual,
            "missing_arguments": sorted(set(expected) - set(actual)),
            "unexpected_arguments": sorted(set(actual) - set(expected)),
            "status": "PASS" if tuple(actual) == tuple(expected) else "FAIL",
        }
    return output
