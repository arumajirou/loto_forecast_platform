from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

NATIVE_QUANTILE_LEVELS = tuple(round(index / 10, 1) for index in range(1, 10))
SOURCE_REVISION = "44ea4e88852228039564aa3e76fac26aafac0803"
MODEL_CLASS = "Toto2Model"
MODEL_LICENSE = "Apache-2.0"
TOTO_MODELS_VERSION = "1.0.0"
TOTO_2_VERSION = "2.0.0"


@dataclass(frozen=True)
class Toto2ArtifactPin:
    name: str
    sha256: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class Toto2VariantManifest:
    model_id: str
    repo_id: str
    model_revision: str
    source_revision: str
    model_class: str
    model_parameter_count: int | None
    model_parameter_count_label: str
    model_parameter_count_verified: bool
    model_license: str
    toto_models_version: str
    toto_2_version: str
    native_quantile_levels: tuple[float, ...]
    artifacts: tuple[Toto2ArtifactPin, ...]
    snapshot_validation_ready: bool
    runtime_scope: str
    runtime_certified: bool = False
    accuracy_certified: bool = False
    lottery_domain_compatibility_certified: bool = False

    def artifact_sha256(self) -> dict[str, str]:
        return {artifact.name: artifact.sha256 for artifact in self.artifacts}

    def artifact_size_bytes(self) -> dict[str, int]:
        return {
            artifact.name: artifact.size_bytes
            for artifact in self.artifacts
            if artifact.size_bytes is not None
        }


TOTO2_4M = Toto2VariantManifest(
    model_id="toto-2.0-4m",
    repo_id="Datadog/Toto-2.0-4m",
    model_revision="8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9",
    source_revision=SOURCE_REVISION,
    model_class=MODEL_CLASS,
    model_parameter_count=4_144_448,
    model_parameter_count_label="4,144,448",
    model_parameter_count_verified=True,
    model_license=MODEL_LICENSE,
    toto_models_version=TOTO_MODELS_VERSION,
    toto_2_version=TOTO_2_VERSION,
    native_quantile_levels=NATIVE_QUANTILE_LEVELS,
    artifacts=(
        Toto2ArtifactPin(
            name="README.md",
            sha256="c8f85b01eae1b586a742d9a0065df252bfe5855644f595969ca111bc206fcfcd",
        ),
        Toto2ArtifactPin(
            name="config.json",
            sha256="7a926d130e401ab0c5fdb3564f46c8d917bd05c7b3ae26b9c22d2da2ef01d2d8",
        ),
        Toto2ArtifactPin(
            name="model.safetensors",
            sha256="316660d5afb47943e531f39242e0b02ca0b8bb73be5709dfe07ca80dfce9805e",
            size_bytes=16_582_848,
        ),
    ),
    snapshot_validation_ready=True,
    runtime_scope="ISOLATED_PROVIDER_ONLY",
)

TOTO2_22M = Toto2VariantManifest(
    model_id="toto-2.0-22m",
    repo_id="Datadog/Toto-2.0-22m",
    model_revision="3affccf372ff82f5d200ac76fad3dbcdeb64299a",
    source_revision=SOURCE_REVISION,
    model_class=MODEL_CLASS,
    model_parameter_count=21_915_584,
    model_parameter_count_label="21,915,584",
    model_parameter_count_verified=True,
    model_license=MODEL_LICENSE,
    toto_models_version=TOTO_MODELS_VERSION,
    toto_2_version=TOTO_2_VERSION,
    native_quantile_levels=NATIVE_QUANTILE_LEVELS,
    artifacts=(
        Toto2ArtifactPin(
            name=".gitattributes",
            sha256="11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361",
            size_bytes=1_519,
        ),
        Toto2ArtifactPin(
            name="README.md",
            sha256="ec40d6b5978fe1ed22e92abe5f9033b5147fc474209dc245df3b4fb8d4dfbf4c",
            size_bytes=352,
        ),
        Toto2ArtifactPin(
            name="config.json",
            sha256="abeaf0fcd54aaac66757fde69ec3ddb4d3bfdcf96e0c8f767aefd03ab4c9e8d9",
            size_bytes=593,
        ),
        Toto2ArtifactPin(
            name="model.safetensors",
            sha256="9cd503d82df3aa71747862688f47a31c1d0a4b80f898df6e046189016eaa21dd",
            size_bytes=87_669_368,
        ),
    ),
    snapshot_validation_ready=True,
    runtime_scope="ISOLATED_PROVIDER_ONLY",
)

TOTO2_VARIANTS: Mapping[str, Toto2VariantManifest] = MappingProxyType(
    {
        TOTO2_4M.model_id: TOTO2_4M,
        TOTO2_22M.model_id: TOTO2_22M,
    }
)


def get_toto2_variant(model_id: str) -> Toto2VariantManifest:
    try:
        return TOTO2_VARIANTS[model_id]
    except KeyError as exc:
        raise ValueError(f"unknown Toto 2.0 variant: {model_id}") from exc
