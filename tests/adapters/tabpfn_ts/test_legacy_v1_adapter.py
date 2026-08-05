from __future__ import annotations

import pytest

from loto.adapters.tabpfn_ts import (
    CheckpointLane,
    TaskFormulation,
    legacy_v1_request_to_v2,
    v2_response_to_legacy_v1,
)
from loto.adapters.tabpfn_ts.manifests import (
    V2_REPO_ID,
    V2_REVISION,
    V2_WEIGHT_FILENAME,
)
from tests.adapters.tabpfn_ts.conftest import build_candidate_response


def _legacy_request() -> dict[str, object]:
    return {
        "schema_version": 1,
        "model_id": "tabpfn_ts",
        "repo_id": V2_REPO_ID,
        "revision": V2_REVISION,
        "weight_filename": V2_WEIGHT_FILENAME,
        "snapshot_path": "/trusted/snapshot",
        "local_files_only": True,
        "device": "cpu",
        "dtype": "float32",
        "history": [
            {
                "draw_date": "2026-01-01",
                "n1": 1,
                "n2": 2,
                "n3": 3,
                "n4": 4,
                "n5": 5,
                "n6": 6,
                "n7": 7,
            },
            {
                "draw_date": "2026-01-08",
                "n1": 2,
                "n2": 3,
                "n3": 4,
                "n4": 5,
                "n5": 6,
                "n6": 7,
                "n7": 8,
            },
        ],
        "prediction_length": 1,
    }


def test_legacy_request_is_explicitly_mapped_to_candidate_lane() -> None:
    request = legacy_v1_request_to_v2(_legacy_request())
    assert request.checkpoint_lane is CheckpointLane.V2_REG_LEGACY
    assert request.task_formulation is TaskFormulation.CANDIDATE_SCORE
    assert len(request.series_ids) == 37
    assert request.history[0].values == [1.0, 0.0]
    assert request.history[7].values == [0.0, 1.0]


def test_legacy_request_rejects_unknown_keys() -> None:
    payload = _legacy_request()
    payload["silent_new_behavior"] = True
    with pytest.raises(ValueError, match="unknown legacy schema-v1 keys"):
        legacy_v1_request_to_v2(payload)


def test_legacy_request_rejects_untrusted_revision() -> None:
    payload = _legacy_request()
    payload["revision"] = "untrusted"
    with pytest.raises(ValueError, match="trusted V2 lane"):
        legacy_v1_request_to_v2(payload)


def test_v2_candidate_response_round_trips_to_schema_v1() -> None:
    response = build_candidate_response()
    payload = response.model_dump(mode="json")
    geometry = payload["effective_arguments"]["game_geometry"]
    geometry.update(
        {
            "game_id": "loto7",
            "position_count": 7,
            "candidate_min": 1,
            "candidate_max": 37,
            "selection_count": 7,
            "strictly_increasing": True,
        }
    )
    payload["series_identity"] = [f"candidate-{candidate:02d}" for candidate in range(1, 38)]
    payload["raw_candidate_scores"] = [
        {"candidate": candidate, "raw_candidate_regression_score": candidate / 100}
        for candidate in range(1, 38)
    ]
    payload["selected_candidates"] = [1, 2, 3, 4, 5, 6, 7]
    converted = v2_response_to_legacy_v1(response.__class__.model_validate(payload))
    assert converted["schema_version"] == 1
    assert converted["prediction_shape"] == [37]
    assert len(converted["predictions"]) == 37
    assert converted["properties"]["output_semantics"] == "raw_candidate_regression_scores"
