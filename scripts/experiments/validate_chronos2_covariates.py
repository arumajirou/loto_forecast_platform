from __future__ import annotations

import sys

import pandas as pd


path = sys.argv[1]
df = pd.read_parquet(path)

ranges = {
    "day_of_week": (0, 6),
    "month_of_year": (1, 12),
    "day_of_month": (1, 31),
    "day_of_year": (1, 366),
    "days_since_previous_draw": (0, 14),
}

errors = []

for column, (lower, upper) in ranges.items():
    if column not in df.columns:
        errors.append(f"missing column: {column}")
        continue

    invalid = df[
        df[column].isna()
        | (df[column] < lower)
        | (df[column] > upper)
    ]

    if not invalid.empty:
        errors.append(
            f"{column}: invalid_rows={len(invalid)} "
            f"min={df[column].min()} max={df[column].max()}"
        )

if errors:
    print("\n".join(errors))
    raise SystemExit(1)

print("COVARIATE_RANGE_VALIDATION=PASS")
