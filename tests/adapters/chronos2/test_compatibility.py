from __future__ import annotations

import pytest

from loto.adapters.chronos2.compatibility import adapt_schema_v1
from loto.adapters.chronos2.manifest import CHRONOS_MODEL_REVISION


def legacy_payload() -> dict[str, object]:
    history = []
    for index in range(3):
        row: dict[str, object] = {
            "draw_no": index + 1,
            "draw_date": f"2026-03-{index + 1:02d}",
        }
        row.update({f"n{i}": i + index for i in range(1, 8)})
        history.append(row)
    return {
        "schema_version": 1,
        "model_id": "chronos-2",
        "revision": CHRONOS_MODEL_REVISION,
        "history": history,
        "device": "cpu",
    }


def test_legacy_loto7_request_is_adapted() -> None:
    request = adapt_schema_v1(legacy_payload())
    assert request.schema_version == 2
    assert request.game_geometry.position_count == 7
    assert request.position_columns[-1] == "n7"
    assert request.seed == 42


def test_legacy_other_revision_is_rejected() -> None:
    payload = legacy_payload()
    payload["revision"] = "0" * 40
    with pytest.raises(ValueError, match="certified legacy revision"):
        adapt_schema_v1(payload)
