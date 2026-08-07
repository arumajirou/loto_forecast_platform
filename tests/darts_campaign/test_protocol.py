from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.darts_campaign.protocol import DartsRequest, GameGeometry


def _geometry() -> dict[str, object]:
    return {"game_id": "numbers4", "positions": 4, "min_value": 0, "max_value": 9}


def test_protocol_rejects_unknown_fields(tmp_path) -> None:
    with pytest.raises(ValidationError):
        DartsRequest.model_validate(
            {
                "run_id": "run-1",
                "mode": "discover",
                "geometry": _geometry(),
                "artifact_dir": tmp_path,
                "unknown": True,
            }
        )


def test_notorch_rejects_cuda(tmp_path) -> None:
    with pytest.raises(ValidationError):
        DartsRequest.model_validate(
            {
                "run_id": "run-1",
                "mode": "discover",
                "geometry": _geometry(),
                "runtime": "notorch",
                "device": "cuda",
                "artifact_dir": tmp_path,
            }
        )


def test_geometry_columns() -> None:
    geometry = GameGeometry.model_validate(_geometry())
    assert geometry.position_columns == ["n1", "n2", "n3", "n4"]
