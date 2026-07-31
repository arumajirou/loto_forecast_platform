from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable

import pandas as pd

from loto.data.lotteries import LotterySpec


def _prime_set(max_n: int) -> set[int]:
    primes: set[int] = set()
    for n in range(2, max_n + 1):
        if all(n % d for d in range(2, int(math.sqrt(n)) + 1)):
            primes.add(n)
    return primes


def _int_values(row: pd.Series, cols: Iterable[str]) -> list[int]:
    vals: list[int] = []
    for c in cols:
        if c not in row or pd.isna(row[c]):
            continue
        vals.append(int(row[c]))
    return vals


def _consecutive_pairs(nums: list[int]) -> int:
    s = set(nums)
    return sum(1 for n in s if n + 1 in s)


def _longest_consecutive_run(nums: list[int]) -> int:
    if not nums:
        return 0
    s = set(nums)
    best = 1
    for n in sorted(s):
        if n - 1 not in s:
            cur = n
            length = 1
            while cur + 1 in s:
                cur += 1
                length += 1
            best = max(best, length)
    return best


def _shannon_entropy(values: list[int]) -> float:
    if not values:
        return 0.0
    c = Counter(values)
    total = len(values)
    return float(-sum((v / total) * math.log2(v / total) for v in c.values()))


def _add_rolling(df: pd.DataFrame, cols: list[str], windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col not in out:
            continue
        shifted = pd.to_numeric(out[col], errors="coerce").shift(1)
        for w in windows:
            roll = shifted.rolling(w, min_periods=1)
            out[f"{col}_lagroll{w}_mean"] = roll.mean()
            out[f"{col}_lagroll{w}_std"] = roll.std().fillna(0.0)
    return out


def make_draw_features(
    df: pd.DataFrame, spec: LotterySpec, windows: list[int] | None = None
) -> pd.DataFrame:
    windows = windows or [5, 10, 20, 50]
    base = (
        df.sort_values(["draw_date", "draw_no"], na_position="last").reset_index(drop=True).copy()
    )
    primes = _prime_set(spec.number_max)

    if spec.kind == "numbers":
        digit_cols = [f"d{i}" for i in range(1, (spec.digits_count or 0) + 1)]
        rows = []
        for _, row in base.iterrows():
            digits = _int_values(row, digit_cols)
            dsum = sum(digits)
            rows.append(
                {
                    "digit_sum": dsum,
                    "digit_mean": dsum / len(digits) if digits else math.nan,
                    "digit_std": pd.Series(digits).std(ddof=0) if digits else math.nan,
                    "digit_range": max(digits) - min(digits) if digits else pd.NA,
                    "digit_even_count": sum(x % 2 == 0 for x in digits),
                    "digit_odd_count": sum(x % 2 == 1 for x in digits),
                    "digit_unique_count": len(set(digits)),
                    "digit_duplicate_count": len(digits) - len(set(digits)),
                    "digit_entropy": _shannon_entropy(digits),
                    "digit_monotonic_inc": int(
                        all(a <= b for a, b in zip(digits, digits[1:], strict=False))
                    ),
                    "digit_monotonic_dec": int(
                        all(a >= b for a, b in zip(digits, digits[1:], strict=False))
                    ),
                }
            )
        feat = pd.concat([base.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
        return _add_rolling(feat, ["digit_sum", "digit_unique_count", "digit_even_count"], windows)

    num_cols = [f"n{i}" for i in range(1, (spec.main_count or 0) + 1)]
    rows = []
    for _, row in base.iterrows():
        nums = sorted(_int_values(row, num_cols))
        gaps = [b - a for a, b in zip(nums, nums[1:], strict=False)]
        low_cut = spec.number_min + (spec.number_max - spec.number_min + 1) / 3
        high_cut = spec.number_min + 2 * (spec.number_max - spec.number_min + 1) / 3
        endings = [n % 10 for n in nums]
        rows.append(
            {
                "num_sum": sum(nums),
                "num_mean": sum(nums) / len(nums) if nums else math.nan,
                "num_std": pd.Series(nums).std(ddof=0) if nums else math.nan,
                "num_min": min(nums) if nums else pd.NA,
                "num_max": max(nums) if nums else pd.NA,
                "num_range": (max(nums) - min(nums)) if nums else pd.NA,
                "num_even_count": sum(n % 2 == 0 for n in nums),
                "num_odd_count": sum(n % 2 == 1 for n in nums),
                "num_prime_count": sum(n in primes for n in nums),
                "num_low_count": sum(n < low_cut for n in nums),
                "num_mid_count": sum(low_cut <= n < high_cut for n in nums),
                "num_high_count": sum(n >= high_cut for n in nums),
                "num_mod0_count": sum(n % 3 == 0 for n in nums),
                "num_mod1_count": sum(n % 3 == 1 for n in nums),
                "num_mod2_count": sum(n % 3 == 2 for n in nums),
                "num_consecutive_pairs": _consecutive_pairs(nums),
                "num_longest_run": _longest_consecutive_run(nums),
                "gap_mean": sum(gaps) / len(gaps) if gaps else 0.0,
                "gap_min": min(gaps) if gaps else 0,
                "gap_max": max(gaps) if gaps else 0,
                "ending_unique_count": len(set(endings)),
                "ending_entropy": _shannon_entropy(endings),
            }
        )
    feat = pd.concat([base.reset_index(drop=True), pd.DataFrame(rows)], axis=1)

    hit_columns: dict[str, pd.Series] = {}
    for n in spec.candidate_numbers:
        hit = base[num_cols].eq(n).any(axis=1).astype(int)
        hit_columns[f"hit_{n:02d}"] = hit
        shifted = hit.shift(1).fillna(0)
        for w in windows:
            hit_columns[f"hit_{n:02d}_lagroll{w}_freq"] = shifted.rolling(w, min_periods=1).sum()
    if hit_columns:
        feat = pd.concat([feat, pd.DataFrame(hit_columns, index=feat.index)], axis=1)

    summary_cols = [
        "num_sum",
        "num_mean",
        "num_range",
        "num_even_count",
        "num_prime_count",
        "num_consecutive_pairs",
        "gap_mean",
        "ending_unique_count",
    ]
    return _add_rolling(feat, summary_cols, windows)


def make_occurrence_features(
    df: pd.DataFrame, spec: LotterySpec, windows: list[int] | None = None
) -> pd.DataFrame:
    """Create long candidate-level features for lotto/bingo games.

    Each row is one candidate number at one draw. `target_hit_next` is useful for
    supervised learning that predicts whether the candidate appears in the next draw.
    """
    if spec.kind == "numbers":
        return pd.DataFrame()
    windows = windows or [5, 10, 20, 50]
    base = (
        df.sort_values(["draw_date", "draw_no"], na_position="last").reset_index(drop=True).copy()
    )
    num_cols = [f"n{i}" for i in range(1, (spec.main_count or 0) + 1)]
    records: list[dict[str, object]] = []
    last_seen: dict[int, int | None] = {n: None for n in spec.candidate_numbers}
    history_hits: dict[int, list[int]] = {n: [] for n in spec.candidate_numbers}

    for idx, row in base.iterrows():
        nums = set(_int_values(row, num_cols))
        next_nums = set(_int_values(base.iloc[idx + 1], num_cols)) if idx + 1 < len(base) else set()
        for n in spec.candidate_numbers:
            hist = history_hits[n]
            rec: dict[str, object] = {
                "game": spec.key,
                "draw_no": row.get("draw_no"),
                "draw_date": row.get("draw_date"),
                "candidate_number": n,
                "hit_current": int(n in nums),
                "target_hit_next": int(n in next_nums) if idx + 1 < len(base) else pd.NA,
                "gap_since_seen": idx - last_seen[n] if last_seen[n] is not None else pd.NA,
                "candidate_mod3": n % 3,
                "candidate_mod10": n % 10,
                "candidate_is_even": int(n % 2 == 0),
            }
            for w in windows:
                rec[f"freq_last_{w}"] = sum(hist[-w:])
                rec[f"seen_last_{w}"] = int(any(hist[-w:]))
            records.append(rec)
        for n in spec.candidate_numbers:
            hit = int(n in nums)
            history_hits[n].append(hit)
            if hit:
                last_seen[n] = idx
    return pd.DataFrame.from_records(records)
