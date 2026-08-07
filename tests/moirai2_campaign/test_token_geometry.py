import pytest

from loto.moirai2_campaign.token_geometry import (
    TokenGeometryError,
    calculate_token_geometry,
)


def test_loto7_context_128_horizons_fit_token_budget() -> None:
    for horizon in (1, 2, 5):
        geometry = calculate_token_geometry(
            target_dim=7,
            context_length=128,
            prediction_length=horizon,
        )
        assert geometry.total_tokens == 63
        assert geometry.total_tokens <= geometry.max_sequence_tokens


def test_oversized_multivariate_context_fails_closed() -> None:
    with pytest.raises(TokenGeometryError, match="total token count"):
        calculate_token_geometry(
            target_dim=64,
            context_length=512,
            prediction_length=5,
        )
