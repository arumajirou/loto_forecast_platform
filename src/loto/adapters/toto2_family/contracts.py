from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from loto.adapters.toto2_4m.contracts import (
    Operation,
    Toto2ProviderRequest,
    Toto2ProviderResponse,
)
from loto.toto2_campaign.variant_manifest import (
    TOTO2_4M,
    Toto2VariantManifest,
    get_toto2_variant,
)


class Toto2VariantContractState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    repo_id: str
    revision: str
    source_revision: str
    model_license: str
    snapshot_validation_ready: bool
    runtime_scope: str
    runtime_certified: bool

    @classmethod
    def from_manifest(cls, manifest: Toto2VariantManifest) -> Toto2VariantContractState:
        return cls(
            model_id=manifest.model_id,
            repo_id=manifest.repo_id,
            revision=manifest.model_revision,
            source_revision=manifest.source_revision,
            model_license=manifest.model_license,
            snapshot_validation_ready=manifest.snapshot_validation_ready,
            runtime_scope=manifest.runtime_scope,
            runtime_certified=manifest.runtime_certified,
        )

    @classmethod
    def from_model_id(cls, model_id: str) -> Toto2VariantContractState:
        return cls.from_manifest(get_toto2_variant(model_id))


class Toto2FamilyProviderRequest(Toto2ProviderRequest):
    model_id: str = TOTO2_4M.model_id
    repo_id: str = TOTO2_4M.repo_id
    revision: str = TOTO2_4M.model_revision
    source_revision: str = TOTO2_4M.source_revision
    model_license: str = TOTO2_4M.model_license

    @model_validator(mode="after")
    def validate_variant_identity(self) -> Toto2FamilyProviderRequest:
        manifest = get_toto2_variant(self.model_id)
        expected = {
            "repo_id": manifest.repo_id,
            "revision": manifest.model_revision,
            "source_revision": manifest.source_revision,
            "model_license": manifest.model_license,
        }
        for field_name, expected_value in expected.items():
            if getattr(self, field_name) != expected_value:
                raise ValueError(f"{field_name} does not match the reviewed Toto 2.0 variant")
        if self.operation is Operation.PREDICT:
            if not manifest.snapshot_validation_ready:
                raise ValueError(
                    "predict is blocked until complete snapshot validation is ready "
                    f"for {manifest.model_id}"
                )
            if not manifest.runtime_certified:
                raise ValueError(
                    "predict is blocked until formal runtime certification is complete "
                    f"for {manifest.model_id}"
                )
        return self


class Toto2FamilyProviderResponse(Toto2ProviderResponse):
    variant_state: Toto2VariantContractState
