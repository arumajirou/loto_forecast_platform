from __future__ import annotations

from typing import Any

from .p6_contract import (
    DistributionMode,
    ModelResourceLimits,
    ModelSpec,
    TrainerKind,
    sha256_json,
)

EXPECTED_MODELS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)

LIGHTNING_TRAINER = {
    "max_epochs": 1,
    "accelerator": "cpu",
    "devices": 1,
    "enable_progress_bar": False,
    "logger": False,
}


def _spec(
    model_class: str,
    module_path: str,
    source_path: str,
    trainer_kind: TrainerKind,
    distribution_mode: DistributionMode,
    supports_context_length: bool,
    default_context_length: int,
    min_target_length: int,
    required: list[str],
    profile: dict[str, Any],
) -> ModelSpec:
    certified = {
        DistributionMode.STUDENT_T: ["StudentTOutput"],
        DistributionMode.QUANTILE: ["QuantileOutput"],
        DistributionMode.INTRINSIC: ["INTRINSIC"],
    }[distribution_mode]
    return ModelSpec(
        model_class=model_class,
        module_path=module_path,
        source_path=source_path,
        trainer_kind=trainer_kind,
        distribution_mode=distribution_mode,
        certified_distributions=certified,
        supports_context_length=supports_context_length,
        default_context_length=default_context_length,
        min_target_length=min_target_length,
        required_constructor_parameters=required,
        constructor_profile=profile,
        resource_limits=ModelResourceLimits(),
    )


def model_specs() -> list[ModelSpec]:
    specs = [
        _spec(
            "DeepNPTSEstimator",
            "gluonts.torch.model.deep_npts",
            "src/gluonts/torch/model/deep_npts/_estimator.py",
            TrainerKind.NATIVE_EPOCH,
            DistributionMode.INTRINSIC,
            True,
            8,
            32,
            ["freq", "prediction_length", "context_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "context_length": "$context_length",
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "epochs": 1,
            },
        ),
        _spec(
            "DeepAREstimator",
            "gluonts.torch.model.deepar",
            "src/gluonts/torch/model/deepar/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.STUDENT_T,
            True,
            8,
            32,
            ["freq", "prediction_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "context_length": "$context_length",
                "num_layers": 1,
                "hidden_size": 4,
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "num_parallel_samples": 4,
                "distr_output": "$distribution",
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "TiDEEstimator",
            "gluonts.torch.model.tide",
            "src/gluonts/torch/model/tide/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            32,
            ["freq", "prediction_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "SimpleFeedForwardEstimator",
            "gluonts.torch.model.simple_feedforward",
            "src/gluonts/torch/model/simple_feedforward/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            24,
            ["prediction_length"],
            {
                "prediction_length": "$prediction_length",
                "hidden_dimensions": [4],
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "TemporalFusionTransformerEstimator",
            "gluonts.torch.model.tft",
            "src/gluonts/torch/model/tft/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.STUDENT_T,
            False,
            8,
            32,
            ["freq", "prediction_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "num_heads": 1,
                "hidden_dim": 4,
                "variable_dim": 4,
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "distr_output": "$distribution",
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "WaveNetEstimator",
            "gluonts.torch.model.wavenet",
            "src/gluonts/torch/model/wavenet/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            32,
            ["freq", "prediction_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "num_parallel_samples": 4,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "DLinearEstimator",
            "gluonts.torch.model.d_linear",
            "src/gluonts/torch/model/d_linear/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            24,
            ["prediction_length"],
            {
                "prediction_length": "$prediction_length",
                "hidden_dimension": 4,
                "kernel_size": 3,
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "PatchTSTEstimator",
            "gluonts.torch.model.patch_tst",
            "src/gluonts/torch/model/patch_tst/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            32,
            ["prediction_length", "patch_len"],
            {
                "prediction_length": "$prediction_length",
                "patch_len": 16,
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
        _spec(
            "LagTSTEstimator",
            "gluonts.torch.model.lag_tst",
            "src/gluonts/torch/model/lag_tst/estimator.py",
            TrainerKind.LIGHTNING,
            DistributionMode.INTRINSIC,
            False,
            8,
            32,
            ["freq", "prediction_length"],
            {
                "freq": "$freq",
                "prediction_length": "$prediction_length",
                "batch_size": 4,
                "num_batches_per_epoch": 1,
                "trainer_kwargs": "$trainer_kwargs",
            },
        ),
    ]
    names = tuple(spec.model_class for spec in specs)
    if names != EXPECTED_MODELS:
        raise RuntimeError("P6 model registry order or membership changed")
    return specs


def get_model_spec(model_class: str) -> ModelSpec:
    for spec in model_specs():
        if spec.model_class == model_class:
            return spec
    raise KeyError(model_class)


def model_spec_sha256(spec: ModelSpec) -> str:
    return sha256_json(spec.model_dump(mode="json"))


def registry_sha256() -> str:
    return sha256_json([spec.model_dump(mode="json") for spec in model_specs()])


def registry_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "models": [spec.model_dump(mode="json") for spec in model_specs()],
        "registry_sha256": registry_sha256(),
        "official_source_tags": ["v0.16.3", "v0.17.0"],
        "official_fixture": "test/torch/model/test_estimators.py",
        "constructor_change_between_tags": False,
    }
