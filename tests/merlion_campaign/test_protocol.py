from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.merlion_campaign.protocol import Operation, ProviderRequest, SeriesPayload


def test_protocol_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderRequest.model_validate(
            {
                "request_id": "case-1",
                "operation": "identity",
                "unexpected": True,
            }
        )


def test_protocol_rejects_path_traversal() -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            request_id="case-1",
            operation=Operation.IDENTITY,
            artifact_subdir="../outside",
        )


def test_train_save_requires_series() -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            request_id="case-1",
            operation=Operation.TRAIN_SAVE,
            model_name="Arima",
        )


def test_valid_train_request() -> None:
    request = ProviderRequest(
        request_id="case-1",
        operation=Operation.TRAIN_SAVE,
        model_name="MSES",
        series=SeriesPayload(name="y", values=[1.0, 2.0, 3.0], draw_numbers=[1, 2, 3]),
    )
    assert request.model_name == "MSES"


def test_protocol_rejects_coerced_draw_numbers() -> None:
    with pytest.raises(ValidationError):
        SeriesPayload(
            name="y",
            values=[1.0, 2.0, 3.0],
            draw_numbers=["1", "2", "3"],
        )


def test_protocol_rejects_dot_path_segment() -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            request_id="case-2",
            operation=Operation.IDENTITY,
            artifact_subdir="model/./nested",
        )
