"""Canonical Loto7 data validation and deterministic projections."""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from loto.contracts import DatasetManifest
from loto.plugins.base import LOTO7

NUMBER_COLS = [f"n{i}" for i in range(1, 8)]
REQUIRED_COLS = ["draw_no", "draw_date", *NUMBER_COLS]


class CanonicalDataError(ValueError):
    pass


def _frame_hash(df: pd.DataFrame) -> str:
    normalized = df.copy()
    for col in normalized.select_dtypes(include=["datetime", "datetimetz"]).columns:
        normalized[col] = normalized[col].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    payload = normalized.to_json(orient="records", date_format="iso", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonicalize_loto7(
    df: pd.DataFrame, source: str = "user-supplied"
) -> tuple[pd.DataFrame, DatasetManifest]:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise CanonicalDataError(f"missing required columns: {missing}")
    out = df[REQUIRED_COLS + [c for c in ("bonus1", "bonus2") if c in df.columns]].copy()
    try:
        out["draw_no"] = pd.to_numeric(out["draw_no"], errors="raise").astype(int)
        out["draw_date"] = pd.to_datetime(out["draw_date"], utc=True, errors="raise")
        for col in NUMBER_COLS:
            out[col] = pd.to_numeric(out[col], errors="raise").astype(int)
    except Exception as exc:  # noqa: BLE001
        raise CanonicalDataError(f"invalid data type: {exc}") from exc
    if out["draw_no"].duplicated().any():
        raise CanonicalDataError("duplicate draw_no")
    out = out.sort_values("draw_no").reset_index(drop=True)
    if not out["draw_no"].is_monotonic_increasing:
        raise CanonicalDataError("draw_no must be increasing")
    if not out["draw_date"].is_monotonic_increasing:
        raise CanonicalDataError("draw_date must be non-decreasing")
    for _idx, row in out.iterrows():
        numbers = [int(row[c]) for c in NUMBER_COLS]
        try:
            LOTO7.validate_numbers(numbers)
        except ValueError as exc:
            raise CanonicalDataError(f"draw_no={row['draw_no']}: {exc}") from exc
    out.insert(0, "draw_id", out["draw_no"].map(lambda x: f"loto7-{x}"))
    out["available_at"] = out["draw_date"]
    sha = _frame_hash(out)
    version = f"loto7-{out['draw_no'].min()}-{out['draw_no'].max()}-{sha[:12]}"
    manifest = DatasetManifest(
        dataset_id="loto7-canonical",
        data_version=version,
        row_count=len(out),
        first_draw_no=int(out["draw_no"].min()) if len(out) else None,
        last_draw_no=int(out["draw_no"].max()) if len(out) else None,
        first_draw_date=out["draw_date"].min().to_pydatetime() if len(out) else None,
        last_draw_date=out["draw_date"].max().to_pydatetime() if len(out) else None,
        sha256=sha,
        source=source,
    )
    return out, manifest


def to_position_table(master: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for rec in master.to_dict("records"):
        for pos, col in enumerate(NUMBER_COLS, start=1):
            rows.append(
                {
                    "draw_id": rec["draw_id"],
                    "draw_no": rec["draw_no"],
                    "draw_date": rec["draw_date"],
                    "position": pos,
                    "number": int(rec[col]),
                    "available_at": rec["available_at"],
                }
            )
    return pd.DataFrame(rows)


def to_candidate_table(master: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for rec in master.to_dict("records"):
        positions = {int(rec[col]): pos for pos, col in enumerate(NUMBER_COLS, start=1)}
        for candidate in range(1, 38):
            rows.append(
                {
                    "draw_id": rec["draw_id"],
                    "draw_no": rec["draw_no"],
                    "draw_date": rec["draw_date"],
                    "candidate_number": candidate,
                    "selected": int(candidate in positions),
                    "position_if_selected": positions.get(candidate),
                    "available_at": rec["available_at"],
                }
            )
    return pd.DataFrame(rows)


def save_manifest(manifest: DatasetManifest, path) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
