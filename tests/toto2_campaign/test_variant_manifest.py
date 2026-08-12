from __future__ import annotations

import pytest

from loto.toto2_campaign.model_manifest import (
    ARTIFACT_SHA256,
    ARTIFACT_SIZE_BYTES,
    MODEL_ID,
    MODEL_PARAMETER_COUNT,
    MODEL_REVISION,
    REPO_ID,
    Toto2ModelManifest,
)
from loto.toto2_campaign.variant_manifest import (
    TOTO2_4M,
    TOTO2_22M,
    TOTO2_VARIANTS,
    get_toto2_variant,
)


def test_legacy_4m_manifest_is_byte_identity_compatible() -> None:
    manifest = Toto2ModelManifest()

    assert MODEL_ID == TOTO2_4M.model_id == "toto-2.0-4m"
    assert REPO_ID == TOTO2_4M.repo_id == "Datadog/Toto-2.0-4m"
    assert MODEL_REVISION == TOTO2_4M.model_revision
    assert MODEL_PARAMETER_COUNT == TOTO2_4M.model_parameter_count == 4_144_448
    assert ARTIFACT_SHA256 == TOTO2_4M.artifact_sha256()
    assert ARTIFACT_SIZE_BYTES == TOTO2_4M.artifact_size_bytes()
    assert manifest.model_id == MODEL_ID
    assert manifest.repo_id == REPO_ID
    assert manifest.runtime_scope == "ISOLATED_PROVIDER_ONLY"


def test_22m_provenance_is_pinned_but_not_runtime_certified() -> None:
    manifest = get_toto2_variant("toto-2.0-22m")

    assert manifest is TOTO2_22M
    assert manifest.repo_id == "Datadog/Toto-2.0-22m"
    assert manifest.model_revision == "3affccf372ff82f5d200ac76fad3dbcdeb64299a"
    assert manifest.model_license == "Apache-2.0"
    assert manifest.model_parameter_count is None
    assert manifest.model_parameter_count_label == "21.9M (official Hub metadata)"
    assert manifest.model_parameter_count_verified is False
    assert manifest.artifact_sha256()["model.safetensors"] == (
        "9cd503d82df3aa71747862688f47a31c1d0a4b80f898df6e046189016eaa21dd"
    )
    assert manifest.artifact_size_bytes()["model.safetensors"] == 87_669_368
    assert manifest.snapshot_validation_ready is False
    assert manifest.runtime_scope == "PROVENANCE_ONLY"
    assert manifest.runtime_certified is False
    assert manifest.accuracy_certified is False
    assert manifest.lottery_domain_compatibility_certified is False


def test_family_manifest_contains_only_reviewed_variants() -> None:
    assert set(TOTO2_VARIANTS) == {"toto-2.0-4m", "toto-2.0-22m"}


def test_unknown_variant_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown Toto 2.0 variant"):
        get_toto2_variant("toto-2.0-313m")
