from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.toto2_family.contracts import (
    Toto2FamilyProviderRequest,
    Toto2FamilyProviderResponse,
    Toto2VariantContractState,
)
from loto.toto2_campaign.geometry import geometry_for_game
from loto.toto2_campaign.variant_manifest import TOTO2_4M, TOTO2_22M


def identity_payload(model_id: str) -> dict[str, object]:
    manifest = TOTO2_4M if model_id == TOTO2_4M.model_id else TOTO2_22M
    geometry = geometry_for_game("numbers3")
    return {
        "schema_version": 2,
        "run_id": "family-contract-test",
        "operation": "identity",
        "model_id": manifest.model_id,
        "repo_id": manifest.repo_id,
        "revision": manifest.model_revision,
        "source_revision": manifest.source_revision,
        "model_license": manifest.model_license,
        "game_geometry": {
            "game_id": geometry.game_id,
            "position_count": geometry.position_count,
            "candidate_min": geometry.candidate_min,
            "candidate_max": geometry.candidate_max,
            "strictly_increasing": geometry.strictly_increasing,
        },
        "series_layout": "position_multivariate",
        "position_columns": ["p1", "p2", "p3"],
    }


def predict_payload(model_id: str) -> dict[str, object]:
    payload = identity_payload(model_id)
    payload.update(
        {
            "operation": "predict",
            "context_length": 1,
            "history": [{"p1": 1.0, "p2": 2.0, "p3": 3.0}],
        }
    )
    return payload


def test_family_contract_accepts_reviewed_4m_and_22m_identity() -> None:
    for model_id in (TOTO2_4M.model_id, TOTO2_22M.model_id):
        request = Toto2FamilyProviderRequest.model_validate(identity_payload(model_id))
        assert request.model_id == model_id


def test_22m_predict_stays_blocked_after_snapshot_verification() -> None:
    assert TOTO2_22M.snapshot_validation_ready is True
    assert TOTO2_22M.runtime_certified is False
    with pytest.raises(ValidationError, match="formal runtime certification"):
        Toto2FamilyProviderRequest.model_validate(predict_payload(TOTO2_22M.model_id))


def test_family_predict_requires_formal_runtime_certification_for_every_variant() -> None:
    assert TOTO2_4M.runtime_certified is False
    with pytest.raises(ValidationError, match="formal runtime certification"):
        Toto2FamilyProviderRequest.model_validate(predict_payload(TOTO2_4M.model_id))


def test_family_contract_rejects_cross_variant_repo_identity() -> None:
    payload = identity_payload(TOTO2_22M.model_id)
    payload["repo_id"] = TOTO2_4M.repo_id
    with pytest.raises(ValidationError, match="repo_id"):
        Toto2FamilyProviderRequest.model_validate(payload)


def test_family_contract_rejects_unreviewed_variant() -> None:
    payload = identity_payload(TOTO2_22M.model_id)
    payload["model_id"] = "toto-2.0-313m"
    with pytest.raises(ValidationError, match="unknown Toto 2.0 variant"):
        Toto2FamilyProviderRequest.model_validate(payload)


def test_family_response_separates_snapshot_and_runtime_state() -> None:
    state = Toto2VariantContractState.from_model_id(TOTO2_22M.model_id)
    response = Toto2FamilyProviderResponse(
        status="BLOCKED",
        phase="runtime_certification",
        message="formal runtime certification is blocked by WSL NVML process visibility",
        variant_state=state,
    )

    assert response.variant_state.model_id == TOTO2_22M.model_id
    assert response.variant_state.snapshot_validation_ready is True
    assert response.variant_state.runtime_certified is False
