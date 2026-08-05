from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.adapters.timesfm25.contracts import BASE_MODEL_ID, Backend

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "timesfm25_campaign" / "model_manifest.json"
)


class BackendManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Backend
    repo_id: str
    revision: str = Field(min_length=40, max_length=40)
    weight_sha256: str = Field(min_length=64, max_length=64)
    environment: str
    runtime_status: str


class PackageProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str
    version: str
    wheel_sha256: str = Field(min_length=64, max_length=64)
    sdist_sha256: str = Field(min_length=64, max_length=64)
    source_revision: str = Field(min_length=40, max_length=40)


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    base_model_id: str = BASE_MODEL_ID
    algorithm_identity: str = BASE_MODEL_ID
    package_provenance: PackageProvenance
    backends: dict[Backend, BackendManifest]
    supports_batched_univariate: bool = True
    supports_joint_multivariate: bool = False
    supports_cross_series_attention: bool = False
    formal_horizons: list[int] = Field(default_factory=lambda: [1, 2, 5])

    @model_validator(mode="after")
    def validate_backend_identity(self) -> ModelManifest:
        for key, backend in self.backends.items():
            if key != backend.backend:
                raise ValueError("backend manifest key and backend field must match")
        if self.algorithm_identity != self.base_model_id:
            raise ValueError("algorithm identity must remain shared across backends")
        return self


def load_manifest(path: Path) -> ModelManifest:
    return ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_default_manifest() -> ModelManifest:
    return load_manifest(DEFAULT_MANIFEST_PATH)


def dump_manifest(manifest: ModelManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    path.write_text(payload, encoding="utf-8")
