from __future__ import annotations

from loto.adapters.chronos2.geometry import game_geometry_preset
from loto.adapters.chronos2.manifest import CHRONOS_MODEL_REVISION
from loto.chronos2_campaign.provider import execute_request


def test_identity_does_not_load_model() -> None:
    geometry, columns = game_geometry_preset("loto7")
    response = execute_request(
        {
            "schema_version": 2,
            "run_id": "identity-test",
            "operation": "identity",
            "revision": CHRONOS_MODEL_REVISION,
            "game_geometry": geometry.model_dump(mode="json"),
            "series_layout": "position_local",
            "position_columns": columns,
            "history": [],
            "device": "cpu",
            "local_files_only": True,
        },
        pipeline_loader=lambda _: (_ for _ in ()).throw(AssertionError("must not load")),
    )
    assert response.status == "OK"
    assert response.model_identity["package_version"] == "2.3.1"


def test_invalid_payload_returns_structured_error() -> None:
    response = execute_request({"schema_version": 2, "run_id": "bad"})
    assert response.status == "ERROR"
    assert response.error is not None
    assert response.error["type"]
