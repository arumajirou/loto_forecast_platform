from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from loto.data.payouts.contracts import PayoutFact, RawPayoutSnapshot


class PayoutColumnMap(BaseModel):
    """Explicit source-column mapping; no heuristic fallback is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draw_no: str = Field(min_length=1)
    tier: str = Field(min_length=1)
    winner_count: str = Field(min_length=1)
    draw_date: str | None = None
    prize_per_winner_jpy: str | None = None
    sales_amount_jpy: str | None = None
    carryover_jpy: str | None = None


def _integer(value: object, field: str, *, allow_missing: bool = False) -> int | None:
    if pd.isna(value):
        if allow_missing:
            return None
        raise ValueError(f"{field} is required")
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer, not bool")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    else:
        text = unicodedata.normalize("NFKC", str(value)).strip().replace(",", "")
        match = re.search(r"-?\d+", text)
        if match is None:
            raise ValueError(f"{field} does not contain an integer: {value!r}")
        result = int(match.group(0))
    if result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _date_string(value: object) -> str | None:
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.date().isoformat()


def normalize_payout_dataframe(
    frame: pd.DataFrame,
    *,
    game: str,
    columns: PayoutColumnMap,
    snapshot: RawPayoutSnapshot,
) -> list[PayoutFact]:
    """Normalize an explicitly mapped source table into immutable payout facts.

    This function intentionally does not guess column names. A changed publisher format must be
    reviewed and expressed as a new/updated source adapter rather than silently reinterpreted.
    """
    required = [columns.draw_no, columns.tier, columns.winner_count]
    optional = [
        columns.draw_date,
        columns.prize_per_winner_jpy,
        columns.sales_amount_jpy,
        columns.carryover_jpy,
    ]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"missing required payout columns: {missing}")
    configured_missing = [name for name in optional if name is not None and name not in frame.columns]
    if configured_missing:
        raise ValueError(f"configured payout columns are missing: {configured_missing}")

    facts: list[PayoutFact] = []
    seen: set[tuple[int, str]] = set()
    for index, row in frame.reset_index(drop=True).iterrows():
        draw_no = _integer(row[columns.draw_no], "draw_no")
        assert draw_no is not None
        tier = unicodedata.normalize("NFKC", str(row[columns.tier])).strip()
        if not tier:
            raise ValueError(f"row {index}: tier is required")
        key = (draw_no, tier)
        if key in seen:
            raise ValueError(f"duplicate payout fact key: {key}")
        seen.add(key)
        winner_count = _integer(row[columns.winner_count], "winner_count")
        assert winner_count is not None
        facts.append(
            PayoutFact(
                game=game,
                draw_no=draw_no,
                draw_date=_date_string(row[columns.draw_date]) if columns.draw_date else None,
                tier=tier,
                winner_count=winner_count,
                prize_per_winner_jpy=(
                    _integer(
                        row[columns.prize_per_winner_jpy],
                        "prize_per_winner_jpy",
                        allow_missing=True,
                    )
                    if columns.prize_per_winner_jpy
                    else None
                ),
                sales_amount_jpy=(
                    _integer(
                        row[columns.sales_amount_jpy],
                        "sales_amount_jpy",
                        allow_missing=True,
                    )
                    if columns.sales_amount_jpy
                    else None
                ),
                carryover_jpy=(
                    _integer(
                        row[columns.carryover_jpy],
                        "carryover_jpy",
                        allow_missing=True,
                    )
                    if columns.carryover_jpy
                    else None
                ),
                source_url=snapshot.source_url,
                source_observed_at=snapshot.observed_at,
                raw_sha256=snapshot.raw_sha256,
                parser_version=snapshot.parser_version,
            )
        )
    return facts


def payout_facts_dataframe(facts: list[PayoutFact]) -> pd.DataFrame:
    return pd.DataFrame([fact.model_dump(mode="json") for fact in facts])
