from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from loto.moirai2_campaign.model_manifest import (
    MAX_SEQUENCE_TOKENS,
    NUM_PREDICT_TOKENS,
    PATCH_SIZE,
)


class TokenGeometryError(ValueError):
    pass


@dataclass(frozen=True)
class TokenGeometry:
    target_dim: int
    context_length: int
    prediction_length: int
    patch_size: int
    context_tokens_per_variable: int
    prediction_tokens_per_variable: int
    total_tokens: int
    max_sequence_tokens: int
    max_prediction_tokens_per_variable: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def calculate_token_geometry(
    *,
    target_dim: int,
    context_length: int,
    prediction_length: int,
) -> TokenGeometry:
    if min(target_dim, context_length, prediction_length) < 1:
        raise TokenGeometryError(
            "target_dim, context_length and prediction_length must be positive"
        )
    context_tokens = math.ceil(context_length / PATCH_SIZE)
    prediction_tokens = math.ceil(prediction_length / PATCH_SIZE)
    total_tokens = target_dim * (context_tokens + prediction_tokens)
    geometry = TokenGeometry(
        target_dim=target_dim,
        context_length=context_length,
        prediction_length=prediction_length,
        patch_size=PATCH_SIZE,
        context_tokens_per_variable=context_tokens,
        prediction_tokens_per_variable=prediction_tokens,
        total_tokens=total_tokens,
        max_sequence_tokens=MAX_SEQUENCE_TOKENS,
        max_prediction_tokens_per_variable=NUM_PREDICT_TOKENS,
    )
    if prediction_tokens > NUM_PREDICT_TOKENS:
        raise TokenGeometryError(
            f"prediction token count {prediction_tokens} exceeds {NUM_PREDICT_TOKENS}"
        )
    if total_tokens > MAX_SEQUENCE_TOKENS:
        raise TokenGeometryError(f"total token count {total_tokens} exceeds {MAX_SEQUENCE_TOKENS}")
    return geometry
