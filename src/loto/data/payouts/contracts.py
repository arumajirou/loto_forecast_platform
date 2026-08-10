from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from loto.game.geometry import known_games


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RawPayoutSnapshot(StrictModel):
    schema_version: str = "payout-raw-snapshot-v1"
    source_url: str = Field(min_length=1)
    observed_at: datetime
    content_type: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    raw_filename: str = Field(min_length=1)
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_bytes: int = Field(ge=0)

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class PayoutFact(StrictModel):
    schema_version: str = "payout-fact-v1"
    game: str
    draw_no: int = Field(ge=1)
    draw_date: str | None = None
    tier: str = Field(min_length=1)
    winner_count: int = Field(ge=0)
    prize_per_winner_jpy: int | None = Field(default=None, ge=0)
    sales_amount_jpy: int | None = Field(default=None, ge=0)
    carryover_jpy: int | None = Field(default=None, ge=0)
    source_url: str = Field(min_length=1)
    source_observed_at: datetime
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=1)

    @field_validator("game")
    @classmethod
    def known_game(cls, value: str) -> str:
        if value not in set(known_games()):
            raise ValueError(f"unknown game: {value}")
        return value

    @field_validator("source_observed_at")
    @classmethod
    def source_time_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source_observed_at must be timezone-aware")
        return value
