from __future__ import annotations

from dataclasses import asdict, dataclass

MODEL_ID = "toto-2.0-4m"
REPO_ID = "Datadog/Toto-2.0-4m"
MODEL_REVISION = "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"
SOURCE_REVISION = "44ea4e88852228039564aa3e76fac26aafac0803"
MODEL_CLASS = "Toto2Model"
MODEL_PARAMETER_COUNT = 4_144_448
MODEL_LICENSE = "Apache-2.0"
TOTO_MODELS_VERSION = "1.0.0"
TOTO_2_VERSION = "2.0.0"
CERTIFIED_PYTHON_SERIES = "3.12"
CERTIFIED_TORCH_VERSION_PREFIX = "2.13.0"
CERTIFIED_CUDA_VERSION = "13.0"
NATIVE_QUANTILE_LEVELS = tuple(round(index / 10, 1) for index in range(1, 10))

ARTIFACT_SHA256 = {
    "README.md": "c8f85b01eae1b586a742d9a0065df252bfe5855644f595969ca111bc206fcfcd",
    "config.json": "7a926d130e401ab0c5fdb3564f46c8d917bd05c7b3ae26b9c22d2da2ef01d2d8",
    "model.safetensors": "316660d5afb47943e531f39242e0b02ca0b8bb73be5709dfe07ca80dfce9805e",
}
ARTIFACT_SIZE_BYTES = {"model.safetensors": 16_582_848}


@dataclass(frozen=True)
class Toto2ModelManifest:
    model_id: str = MODEL_ID
    repo_id: str = REPO_ID
    model_revision: str = MODEL_REVISION
    source_revision: str = SOURCE_REVISION
    model_class: str = MODEL_CLASS
    model_parameter_count: int = MODEL_PARAMETER_COUNT
    model_license: str = MODEL_LICENSE
    toto_models_version: str = TOTO_MODELS_VERSION
    toto_2_version: str = TOTO_2_VERSION
    native_quantile_levels: tuple[float, ...] = NATIVE_QUANTILE_LEVELS
    runtime_scope: str = "ISOLATED_PROVIDER_ONLY"
    accuracy_certified: bool = False
    lottery_domain_compatibility_certified: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
