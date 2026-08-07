from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from loto.basicts_campaign.protocol import ProviderOperation, ProviderRequest


def test_request_rejects_unknown_keys(tmp_path) -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            operation=ProviderOperation.IDENTITY,
            output_dir=str(tmp_path),
            unknown=True,
        )


def test_request_rejects_nonfinite_series(tmp_path) -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            operation=ProviderOperation.DLINEAR_SMOKE,
            output_dir=str(tmp_path),
            series=[[1.0], [2.0], [3.0], [math.inf]],
            input_len=2,
            output_len=1,
            moving_avg=1,
        )


def test_request_rejects_even_moving_average(tmp_path) -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            operation=ProviderOperation.DLINEAR_SMOKE,
            output_dir=str(tmp_path),
            moving_avg=2,
        )
