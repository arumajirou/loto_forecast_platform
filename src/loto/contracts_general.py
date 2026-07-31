"""Geometry-parameterised contracts.

``contracts.py`` pinned ``ge=1, le=37``, ``min_length=37`` and ``position <= 7`` directly into
pydantic ``Field`` declarations, which made every downstream contract Loto7-only. Pydantic
field constraints are class-level, so the fix is a *factory*: build the model class for a
given :class:`~loto.game.geometry.GameGeometry` and cache it.

The v1 contracts remain importable so existing Loto7 regression tests keep passing; new code
should use :func:`contracts_for`.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from loto.game.geometry import GameGeometry, geometry_for

SCHEMA_VERSION = "3.0.0"

__all__ = ["SCHEMA_VERSION", "GameContracts", "contracts_for"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)
    schema_version: str = SCHEMA_VERSION


class GameContracts:
    """Bundle of contract classes specialised for one game."""

    def __init__(self, geometry: GameGeometry) -> None:
        self.geometry = geometry
        g = geometry

        candidate = create_model(
            f"CandidateProbability_{g.key}",
            __base__=_Strict,
            candidate_number=(int, Field(ge=g.value_min, le=g.value_max)),
            probability=(float, Field(ge=0.0, le=1.0)),
            rank_score=(float, ...),
        )

        position = create_model(
            f"PositionProbability_{g.key}",
            __base__=_Strict,
            position=(int, Field(ge=1, le=g.positions)),
            candidate_number=(int, Field(ge=g.value_min, le=g.value_max)),
            probability=(float, Field(ge=0.0, le=1.0)),
        )

        def _validate_combination(self: Any) -> Any:
            g.validate_outcome(self.values)
            return self

        combination = create_model(
            f"DecodedCombination_{g.key}",
            __base__=_Strict,
            values=(list[int], Field(min_length=g.positions, max_length=g.positions)),
            score=(float, ...),
            __validators__={"_check": model_validator(mode="after")(_validate_combination)},
        )

        width = g.inclusion_vector_length

        def _validate_forecast(self: Any) -> Any:
            numbers = [c.candidate_number for c in self.candidates]
            if g.family == "select" and sorted(numbers) != list(g.values):
                raise ValueError(
                    f"candidates must contain every value in "
                    f"[{g.value_min}, {g.value_max}] exactly once"
                )
            if self.created_at >= self.draw_time:
                raise ValueError("forecast must be created strictly before draw_time")
            return self

        forecast = create_model(
            f"ForecastPackage_{g.key}",
            __base__=_Strict,
            forecast_id=(str, ...),
            draw_id=(str, ...),
            game=(str, Field(default=g.key, pattern=f"^{g.key}$")),
            model_id=(str, ...),
            data_version=(str, ...),
            feature_set_id=(str, ...),
            protocol_hash=(str, Field(min_length=64, max_length=64)),
            created_at=(datetime, ...),
            draw_time=(datetime, ...),
            combination=(combination, ...),
            candidates=(list[candidate], Field(min_length=width, max_length=width)),
            metadata=(dict[str, Any], Field(default_factory=dict)),
            __validators__={"_check": model_validator(mode="after")(_validate_forecast)},
        )

        self.CandidateProbability = candidate
        self.PositionProbability = position
        self.DecodedCombination = combination
        self.ForecastPackage = forecast

    def describe(self) -> dict[str, object]:
        return {
            "game": self.geometry.key,
            "schema_version": SCHEMA_VERSION,
            "positions": self.geometry.positions,
            "value_range": [self.geometry.value_min, self.geometry.value_max],
            "inclusion_vector_length": self.geometry.inclusion_vector_length,
            "models": [
                self.CandidateProbability.__name__,
                self.PositionProbability.__name__,
                self.DecodedCombination.__name__,
                self.ForecastPackage.__name__,
            ],
        }


@lru_cache(maxsize=16)
def contracts_for(game: str) -> GameContracts:
    """Cached contract bundle for ``game``."""
    return GameContracts(geometry_for(game))
