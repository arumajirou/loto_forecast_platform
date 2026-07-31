from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from loto.data.lotteries import LotterySpec

_ENCODINGS = ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp")
_SEPS = (",", "\t", ";")


def _normalize_label(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"\s+", "", text)
    text = text.replace("抽せん", "抽選")
    return text


def read_csv_flexible(path: str | Path) -> tuple[pd.DataFrame, dict[str, str]]:
    path = Path(path)
    last_error: Exception | None = None
    for enc in _ENCODINGS:
        for sep in _SEPS:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep)
                if df.shape[1] >= 2:
                    return df, {"encoding": enc, "sep": sep}
            except Exception as exc:  # noqa: BLE001
                last_error = exc
    raise RuntimeError(f"Could not parse CSV: {path}: {last_error}")


def _find_first_column(df: pd.DataFrame, patterns: Iterable[str]) -> str | None:
    normalized = {_normalize_label(c): str(c) for c in df.columns}
    for pattern in patterns:
        rx = re.compile(pattern)
        for norm, original in normalized.items():
            if rx.search(norm):
                return original
    return None


def _find_number_columns(
    df: pd.DataFrame,
    prefix_patterns: list[str],
    count: int,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    cols: list[tuple[int, str]] = []
    excludes = [re.compile(p) for p in (exclude_patterns or [])]
    for col in df.columns:
        n = _normalize_label(col)
        if any(rx.search(n) for rx in excludes):
            continue
        for base in prefix_patterns:
            # Examples: 本数字1, 第1数字, num1, n1, 数字1
            m = re.search(base + r"(?:0?)(\d+)$", n)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= max(count, 12):
                    cols.append((idx, str(col)))
    seen: set[str] = set()
    ordered = [c for _, c in sorted(cols) if not (c in seen or seen.add(c))]
    return ordered[:count]


def _to_int_or_none(value: object) -> int | None:
    if pd.isna(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    m = re.search(r"\d+", text.replace(",", ""))
    return int(m.group(0)) if m else None


def _split_digits(value: object, digits: int) -> list[int | None]:
    if pd.isna(value):
        return [None] * digits
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\D", "", text)
    if len(text) < digits:
        text = text.zfill(digits)
    return [int(ch) for ch in text[-digits:]]


def _candidate_numeric_columns(df: pd.DataFrame) -> list[str]:
    blocked = re.compile(
        r"(当選|当せん|賞金|口数|金額|販売|売上|キャリー|carry|prize|amount|sales|円|rank|等)"
    )
    candidates: list[str] = []
    for c in df.columns:
        norm = _normalize_label(c)
        if blocked.search(norm):
            continue
        if re.search(r"(回|date|日|id|url|source)", norm):
            continue
        s = df[c].dropna().astype(str).head(20)
        if len(s) == 0:
            continue
        numeric_like = s.map(
            lambda x: bool(re.fullmatch(r"\s*\d+\s*", unicodedata.normalize("NFKC", x)))
        ).mean()
        if numeric_like >= 0.8:
            candidates.append(str(c))
    return candidates


def normalize_raw_dataframe(df: pd.DataFrame, spec: LotterySpec, source_url: str) -> pd.DataFrame:
    out = pd.DataFrame()
    out["game"] = spec.key
    out["game_display_name"] = spec.display_name
    out["source_url"] = source_url

    draw_col = _find_first_column(
        df, [r"^(開催)?回(別|号|数)?$", r"draw", r"round", r"^no$", r"^id$"]
    )
    date_col = _find_first_column(df, [r"抽選日", r"開催日", r"日付", r"date"])

    if draw_col:
        out["draw_no"] = df[draw_col].map(_to_int_or_none).astype("Int64")
    else:
        out["draw_no"] = pd.Series(range(1, len(df) + 1), dtype="Int64")

    if date_col:
        out["draw_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype("string")
    else:
        out["draw_date"] = pd.Series([pd.NA] * len(df), dtype="string")

    if spec.kind == "numbers":
        digit_col = _find_first_column(
            df, [r"抽選数字", r"本数字", r"当選番号", r"当せん番号", r"number", r"digits"]
        )
        digit_cols = _find_number_columns(
            df, [r"d", r"digit", r"数字", r"桁"], spec.digits_count or 0
        )
        if digit_cols and len(digit_cols) >= (spec.digits_count or 0):
            for i, col in enumerate(digit_cols[: spec.digits_count or 0], start=1):
                out[f"d{i}"] = df[col].map(_to_int_or_none).astype("Int64")
        elif digit_col:
            split = df[digit_col].map(lambda x: _split_digits(x, spec.digits_count or 0))
            for i in range(spec.digits_count or 0):
                out[f"d{i + 1}"] = split.map(lambda xs, j=i: xs[j]).astype("Int64")
        else:
            candidates = _candidate_numeric_columns(df)[: spec.digits_count or 0]
            for i, col in enumerate(candidates, start=1):
                out[f"d{i}"] = df[col].map(_to_int_or_none).astype("Int64")
        return _add_calendar(out)

    main_cols = _find_number_columns(
        df,
        [r"本数字", r"第", r"num", r"number", r"n", r"数字", r"ボール"],
        spec.main_count or 0,
        exclude_patterns=[r"ボーナス", r"bonus", r"当選", r"当せん", r"賞金", r"金額", r"口数"],
    )
    if len(main_cols) < (spec.main_count or 0):
        candidates = _candidate_numeric_columns(df)
        # Keep range-valid columns only when possible.
        filtered = []
        for col in candidates:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) and vals.between(spec.number_min, spec.number_max).mean() >= 0.9:
                filtered.append(col)
        main_cols = filtered[: spec.main_count or 0]

    for i in range(spec.main_count or 0):
        col = main_cols[i] if i < len(main_cols) else None
        out[f"n{i + 1}"] = df[col].map(_to_int_or_none).astype("Int64") if col else pd.NA

    bonus_cols = _find_number_columns(df, [r"ボーナス数字", r"bonus", r"b"], spec.bonus_count)
    if len(bonus_cols) < spec.bonus_count:
        # If the CSV places bonus numbers after the main numbers,
        # use remaining valid numeric columns.
        candidates = [c for c in _candidate_numeric_columns(df) if c not in main_cols]
        bonus_cols = (bonus_cols + candidates)[: spec.bonus_count]
    for i in range(spec.bonus_count):
        col = bonus_cols[i] if i < len(bonus_cols) else None
        out[f"bonus{i + 1}"] = df[col].map(_to_int_or_none).astype("Int64") if col else pd.NA

    return _add_calendar(out)


def _add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    parsed = pd.to_datetime(df["draw_date"], errors="coerce")
    df["year"] = parsed.dt.year.astype("Int64")
    df["month"] = parsed.dt.month.astype("Int64")
    df["day"] = parsed.dt.day.astype("Int64")
    df["weekday"] = parsed.dt.weekday.astype("Int64")
    df["is_month_start"] = parsed.dt.is_month_start.fillna(False).astype(bool)
    df["is_month_end"] = parsed.dt.is_month_end.fillna(False).astype(bool)
    return df


def parse_file(raw_path: str | Path, spec: LotterySpec) -> tuple[pd.DataFrame, dict[str, str]]:
    raw, meta = read_csv_flexible(raw_path)
    normalized = normalize_raw_dataframe(raw, spec, source_url=spec.url)
    return normalized, meta
