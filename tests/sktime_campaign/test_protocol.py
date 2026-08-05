from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.sktime_campaign.protocol import ProviderOperation, ProviderRequest


def test_inventory_request_uses_pinned_cpu_lane(tmp_path) -> None:
    request = ProviderRequest(
        operation=ProviderOperation.INVENTORY,
        output_dir=str(tmp_path / "inventory"),
    )

    assert request.expected_sktime_version == "1.0.1"
    assert request.environment_lane == "core-py313"
    assert request.device == "cpu"
    assert request.forecast_horizon == [1]


@pytest.mark.parametrize(
    "overrides",
    [
        {"forecast_horizon": [0]},
        {"forecast_horizon": [1, 1]},
        {"forecast_horizon": [2, 1]},
        {"series": [1.0, float("nan"), 3.0]},
        {"series": [1.0, float("inf"), 3.0]},
    ],
)
def test_request_rejects_invalid_time_series_contract(
    tmp_path,
    overrides: dict[str, object],
) -> None:
    payload = {
        "operation": "naive_smoke",
        "output_dir": str(tmp_path / "smoke"),
        **overrides,
    }

    with pytest.raises(ValidationError):
        ProviderRequest.model_validate(payload)


def test_request_rejects_unknown_keys(tmp_path) -> None:
    with pytest.raises(ValidationError):
        ProviderRequest.model_validate(
            {
                "operation": "inventory",
                "output_dir": str(tmp_path / "inventory"),
                "silent_fallback": True,
            }
        )
