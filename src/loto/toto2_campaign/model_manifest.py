from __future__ import annotations

from dataclasses import asdict, dataclass

from loto.toto2_campaign.variant_manifest import (
    MODEL_CLASS,
    MODEL_LICENSE,
    NATIVE_QUANTILE_LEVELS,
    SOURCE_REVISION,
    TOTO2_4M,
    TOTO_2_VERSION,
    TOTO_MODELS_VERSION,
)

MODEL_ID = TOTO2_4M.model_id
REPO_ID = TOTO2_4M.repo_id
MODEL_REVISION = TOTO2_4M.model_revision
MODEL_PARAMETER_COUNT = TOTO2_4M.model_parameter_count
if MODEL_PARAMETER_COUNT is None:
    raise RuntimeError("legacy Toto 2.0 4M parameter count must remain exact")
CERTIFIED_PYTHON_SERIES = "3.12"
CERTIFIED_TORCH_VERSION_PREFIX = "2.13.0"
CERTIFIED_CUDA_VERSION = "13.0"

ARTIFACT_SHA256 = TOTO2_4M.artifact_sha256()
ARTIFACT_SIZE_BYTES = TOTO2_4M.artifact_size_bytes()


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
