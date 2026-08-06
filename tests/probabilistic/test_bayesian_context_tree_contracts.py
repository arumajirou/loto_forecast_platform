from __future__ import annotations

import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.probabilistic.bct_contracts import (
    MODEL_ID,
    BayesianContextTreeChronologyEvidenceV1,
    BayesianContextTreeConfigV1,
    BayesianContextTreeRequestV1,
    BayesianContextTreeResponseV1,
    BayesianContextTreeStateManifestV1,
    bct_config_sha256,
    canonical_payload_sha256,
    load_bct_config,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/probabilistic/bayesian_context_tree.yaml"
EXPECTED_CONFIG_SHA256 = "4f01e804be92374556fc435ed96d2bfe0fa2667e6fd6a9454257d3ff372bc569"


def _chronology(**updates: object) -> BayesianContextTreeChronologyEvidenceV1:
    payload: dict[str, object] = {
        "prediction_created_at": datetime(2026, 8, 6, 2, 30, tzinfo=UTC),
        "history_last_index": 3,
        "prediction_index": 4,
        "actuals_used_through_index": 3,
        "predict_before_update": True,
        "update_after_prediction": True,
        "future_actuals_used": False,
        "actual_known_at_prediction": False,
    }
    payload.update(updates)
    return BayesianContextTreeChronologyEvidenceV1.model_validate(payload)


def _identity() -> dict[str, object]:
    alphabet = ["0", "1", "2"]
    return {
        "run_id": "bct-contract-20260806T023000Z",
        "model_id": MODEL_ID,
        "package_version": "3.2.0",
        "source_revision": "7256534c1617af656e8f3255676a34733225dcb3",
        "model_revision": "UNIMPLEMENTED",
        "config_sha256": "a" * 64,
        "weight_sha256": None,
        "license": "clean-room project code; upstream CRAN BCT is GPL-2-or-later",
        "game": "numbers3",
        "target_layout": "per_position_univariate",
        "alphabet": alphabet,
        "alphabet_sha256": canonical_payload_sha256(alphabet),
        "context_length": 4,
        "prediction_length": 1,
        "max_depth": 4,
        "beta": 0.5,
        "prior_concentration": 0.5,
        "top_k": 5,
        "max_nodes": 1000,
        "seed": 1,
        "requested_device": "cpu",
        "effective_device": "cpu",
        "cpu_fallback": False,
        "actuals_used": [0, 1, 2, 3],
        "chronology_evidence": _chronology(),
    }


def _request_payload() -> dict[str, object]:
    return {
        **_identity(),
        "input_shape": [4],
        "history": ["0", "1", "2", "0"],
    }


def _response_payload() -> dict[str, object]:
    return {
        **_identity(),
        "input_shape": [4],
        "output_shape": [1, 3],
        "point_forecast": ["1"],
        "categorical_probabilities": [[0.2, 0.6, 0.2]],
        "samples": [["1"], ["0"]],
        "finite_check": True,
        "categorical_simplex_check": True,
        "suffix_closure_check": True,
        "runtime_pid": 12345,
        "gpu_uuid": None,
        "gpu_process_vram_mb": None,
        "state_sha256": "b" * 64,
        "prediction_sha256": "c" * 64,
        "artifact_paths": ["artifacts/bct/request.json", "artifacts/bct/response.json"],
    }


def test_valid_request_response_and_serialization_roundtrip() -> None:
    request = BayesianContextTreeRequestV1.model_validate(_request_payload())
    response = BayesianContextTreeResponseV1.model_validate(_response_payload())
    restored_request = BayesianContextTreeRequestV1.model_validate_json(request.model_dump_json())
    restored_response = BayesianContextTreeResponseV1.model_validate_json(
        response.model_dump_json()
    )
    assert restored_request == request
    assert restored_response == response
    assert response.quantiles == {}


def test_state_manifest_roundtrip() -> None:
    payload = {
        **_identity(),
        "implementation_status": "CONTRACT_ONLY",
        "state_sha256": "d" * 64,
        "persisted_at": datetime(2026, 8, 6, 2, 31, tzinfo=UTC),
        "artifact_paths": ["artifacts/bct/state.json", "artifacts/bct/state.npz"],
    }
    state = BayesianContextTreeStateManifestV1.model_validate(payload)
    assert BayesianContextTreeStateManifestV1.model_validate_json(state.model_dump_json()) == state


@pytest.mark.parametrize(
    "artifact_paths",
    [
        ["artifacts/bct/state.txt"],
        ["artifacts/bct/state.json"],
        ["artifacts/bct/state.json", "artifacts/bct/other.json"],
        [
            "artifacts/bct/state.json",
            "artifacts/bct/state.npz",
            "artifacts/bct/extra.txt",
        ],
    ],
)
def test_state_manifest_requires_exact_json_and_npz_artifacts(
    artifact_paths: list[str],
) -> None:
    payload = {
        **_identity(),
        "implementation_status": "CONTRACT_ONLY",
        "state_sha256": "d" * 64,
        "persisted_at": datetime(2026, 8, 6, 2, 31, tzinfo=UTC),
        "artifact_paths": artifact_paths,
    }
    with pytest.raises(ValidationError):
        BayesianContextTreeStateManifestV1.model_validate(payload)


def test_prediction_timestamp_must_be_timezone_aware_utc() -> None:
    with pytest.raises(ValidationError):
        _chronology(prediction_created_at=datetime(2026, 8, 6, 2, 30))
    with pytest.raises(ValidationError):
        _chronology(
            prediction_created_at=datetime(
                2026, 8, 6, 11, 30, tzinfo=timezone(timedelta(hours=9))
            )
        )


def test_state_timestamp_must_be_utc_and_not_precede_prediction() -> None:
    payload = {
        **_identity(),
        "implementation_status": "CONTRACT_ONLY",
        "state_sha256": "d" * 64,
        "persisted_at": datetime(2026, 8, 6, 2, 29, tzinfo=UTC),
        "artifact_paths": ["artifacts/bct/state.json", "artifacts/bct/state.npz"],
    }
    with pytest.raises(ValidationError):
        BayesianContextTreeStateManifestV1.model_validate(payload)
    payload["persisted_at"] = datetime(2026, 8, 6, 2, 31)
    with pytest.raises(ValidationError):
        BayesianContextTreeStateManifestV1.model_validate(payload)


def test_unknown_field_is_rejected() -> None:
    payload = _request_payload()
    payload["unknown_field"] = "forbidden"
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


def test_wrong_model_id_is_rejected() -> None:
    payload = _request_payload()
    payload["model_id"] = "pp-bart-categorical"
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


def test_invalid_sha256_is_rejected() -> None:
    payload = _request_payload()
    payload["config_sha256"] = "not-a-digest"
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


def test_negative_depth_and_invalid_beta_are_rejected() -> None:
    payload = _request_payload()
    payload["max_depth"] = -1
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)
    payload = _request_payload()
    payload["beta"] = 1.0
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_probability_is_rejected(value: float) -> None:
    payload = _response_payload()
    payload["categorical_probabilities"] = [[value, 0.5, 0.5]]
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)


def test_categorical_simplex_and_shape_mismatch_are_rejected() -> None:
    payload = _response_payload()
    payload["categorical_probabilities"] = [[0.2, 0.2, 0.2]]
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)
    payload = _response_payload()
    payload["output_shape"] = [1, 2]
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)


def test_quantiles_must_remain_empty() -> None:
    payload = _response_payload()
    payload["quantiles"] = {"0.5": [1.0]}
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)


def test_cpu_runtime_fields_and_gpu_inconsistency() -> None:
    response = BayesianContextTreeResponseV1.model_validate(_response_payload())
    assert response.requested_device == "cpu"
    assert response.effective_device == "cpu"
    assert response.cpu_fallback is False
    assert response.gpu_uuid is None
    assert response.gpu_process_vram_mb is None
    payload = _response_payload()
    payload["gpu_uuid"] = "GPU-should-not-exist"
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)


def test_future_actual_leakage_is_rejected() -> None:
    payload = _request_payload()
    payload["actuals_used"] = [0, 1, 2, 3, 4]
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)
    with pytest.raises(ValidationError):
        _chronology(future_actuals_used=True)


@pytest.mark.parametrize("actuals_used", [[-1], [3, 2, 1, 0], [0, 1, 1, 2]])
def test_actual_indexes_must_be_nonnegative_unique_and_increasing(
    actuals_used: list[int],
) -> None:
    payload = _request_payload()
    payload["actuals_used"] = actuals_used
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


@pytest.mark.parametrize("actuals_used", [[], [0, 1, 2]])
def test_actual_indexes_must_match_declared_through_index(
    actuals_used: list[int],
) -> None:
    payload = _request_payload()
    payload["actuals_used"] = actuals_used
    with pytest.raises(ValidationError):
        BayesianContextTreeRequestV1.model_validate(payload)


def test_empty_actual_indexes_require_minus_one_through_index() -> None:
    payload = _request_payload()
    payload["actuals_used"] = []
    payload["chronology_evidence"] = _chronology(
        history_last_index=-1,
        actuals_used_through_index=-1,
    )
    request = BayesianContextTreeRequestV1.model_validate(payload)
    assert request.actuals_used == []


@pytest.mark.parametrize(
    "artifact_path",
    [
        "../outside.json",
        "./artifacts/state.json",
        "artifacts//state.json",
        "artifacts/state.json/",
        "artifacts/\nstate.json",
    ],
)
def test_unsafe_or_noncanonical_artifact_paths_are_rejected(artifact_path: str) -> None:
    payload = _response_payload()
    payload["artifact_paths"] = [artifact_path]
    with pytest.raises(ValidationError):
        BayesianContextTreeResponseV1.model_validate(payload)


def test_config_schema_and_sha256_are_deterministic() -> None:
    first = load_bct_config(str(CONFIG_PATH))
    second = BayesianContextTreeConfigV1.model_validate(
        deepcopy(first.model_dump(mode="python"))
    )
    assert first.active_catalog_registration is False
    assert first.implementation_status == "CONTRACT_ONLY"
    digest = bct_config_sha256(first)
    assert digest == EXPECTED_CONFIG_SHA256
    assert digest == bct_config_sha256(second)
    assert len(digest) == 64


def test_active_catalog_and_native_registry_do_not_register_model() -> None:
    paths = [
        ROOT / "configs/probabilistic/catalog.yaml",
        ROOT / "configs/probabilistic/native_primary.yaml",
        ROOT / "src/loto/probabilistic/catalog.py",
        ROOT / "src/loto/probabilistic/native_registry.py",
        ROOT / "src/loto/probabilistic/backends/builtin.py",
    ]
    for path in paths:
        assert MODEL_ID not in path.read_text(encoding="utf-8")
