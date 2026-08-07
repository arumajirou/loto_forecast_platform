from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.toto2_4m.contracts import Toto2ProviderRequest
from loto.toto2_campaign.geometry import geometry_for_game
from loto.toto2_campaign.model_manifest import MODEL_REVISION, REPO_ID, SOURCE_REVISION


def request_payload(game_id: str = "numbers3", rows: int = 8) -> dict[str, object]:
    geometry = geometry_for_game(game_id)
    columns = [f"p{index}" for index in range(1, geometry.position_count + 1)]
    history = [
        {name: float(row + index) for index, name in enumerate(columns)}
        for row in range(rows)
    ]
    return {
        "schema_version": 2,
        "run_id": "contract-test",
        "operation": "predict",
        "model_id": "toto-2.0-4m",
        "repo_id": REPO_ID,
        "revision": MODEL_REVISION,
        "source_revision": SOURCE_REVISION,
        "model_license": "Apache-2.0",
        "game_geometry": {
            "game_id": geometry.game_id,
            "position_count": geometry.position_count,
            "candidate_min": geometry.candidate_min,
            "candidate_max": geometry.candidate_max,
            "strictly_increasing": geometry.strictly_increasing,
        },
        "series_layout": "position_multivariate",
        "position_columns": columns,
        "history": history,
        "timestamps": list(range(100, 100 + rows)),
        "time_semantics": "draw_sequence",
        "context_length": rows,
        "prediction_length": 1,
        "native_quantile_levels": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "point_method": "median_q0.5",
        "batch_size": 1,
        "decode_block_size": 32,
        "device": "cpu",
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": None,
    }


def test_contract_accepts_dynamic_game_geometry() -> None:
    for game_id, count in {
        "numbers3": 3,
        "numbers4": 4,
        "miniloto": 5,
        "loto6": 6,
        "loto7": 7,
    }.items():
        request = Toto2ProviderRequest.model_validate(request_payload(game_id))
        assert request.game_geometry.position_count == count


def test_contract_rejects_unknown_fields() -> None:
    payload = request_payload()
    payload["guessed_runtime_argument"] = True
    with pytest.raises(ValidationError):
        Toto2ProviderRequest.model_validate(payload)


def test_contract_rejects_revision_drift() -> None:
    payload = request_payload()
    payload["revision"] = "0" * 40
    with pytest.raises(ValidationError):
        Toto2ProviderRequest.model_validate(payload)


def test_contract_rejects_non_gap_free_draw_sequence() -> None:
    payload = request_payload()
    payload["timestamps"] = [100, 101, 103, 104, 105, 106, 107, 108]
    with pytest.raises(ValidationError):
        Toto2ProviderRequest.model_validate(payload)


def test_univariate_requires_one_position() -> None:
    payload = request_payload()
    payload["series_layout"] = "position_univariate"
    with pytest.raises(ValidationError):
        Toto2ProviderRequest.model_validate(payload)
