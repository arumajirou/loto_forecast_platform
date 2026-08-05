from __future__ import annotations

from loto.auto_campaign.runner import _config_diff


class RecurrentDummy:
    RECURRENT = True
    h = 1


def test_recurrent_input_sizes_are_recorded_as_normalized() -> None:
    result = _config_diff(
        {
            "h": 1,
            "input_size": -1,
            "inference_input_size": -1,
        },
        {
            "h": 1,
            "input_size": 4,
            "inference_input_size": 4,
        },
        model=RecurrentDummy(),
    )

    assert result["status"] == "PASS"
    assert result["items"]["input_size"]["status"] == "NORMALIZED_BY_MODEL"
    assert result["items"]["inference_input_size"]["status"] == "NORMALIZED_BY_MODEL"
