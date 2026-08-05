from __future__ import annotations

from loto.tirex2_campaign.provenance import (
    MODEL_CONFIG_SHA256,
    MODEL_WEIGHT_SHA256,
    PACKAGE_VERSION,
    SDIST_SHA256,
    SOURCE_ACCESS_STATUS,
    SOURCE_ATTESTATION_COMMIT,
    WHEEL_SHA256,
)


def test_package_and_model_identity_are_exactly_pinned() -> None:
    assert PACKAGE_VERSION == "0.1.1"
    assert len(WHEEL_SHA256) == 64
    assert len(SDIST_SHA256) == 64
    assert len(MODEL_WEIGHT_SHA256) == 64
    assert len(MODEL_CONFIG_SHA256) == 64
    assert len(SOURCE_ATTESTATION_COMMIT) == 40
    assert SOURCE_ACCESS_STATUS == "PYPI_ATTESTED_NOT_FULLY_PUBLICLY_AUDITABLE"
