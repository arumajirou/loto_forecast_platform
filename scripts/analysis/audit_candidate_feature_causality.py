from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


WINDOWS = (5, 10, 20, 30, 50, 100)


def compare_column(
    actual: np.ndarray,
    expected_count: np.ndarray,
    expected_rate: np.ndarray,
) -> dict[str, float | str]:
    finite = np.isfinite(actual)
    if not finite.any():
        return {
            "best_convention": "none",
            "count_match_rate": 0.0,
            "rate_match_rate": 0.0,
            "count_mae": float("nan"),
            "rate_mae": float("nan"),
        }

    actual = actual[finite]
    expected_count = expected_count[finite]
    expected_rate = expected_rate[finite]

    count_match_rate = float(
        np.isclose(actual, expected_count, atol=1e-10).mean()
    )
    rate_match_rate = float(
        np.isclose(actual, expected_rate, atol=1e-10).mean()
    )

    return {
        "best_convention": (
            "prior_count"
            if count_match_rate >= rate_match_rate
            else "prior_rate"
        ),
        "count_match_rate": count_match_rate,
        "rate_match_rate": rate_match_rate,
        "count_mae": float(np.mean(np.abs(actual - expected_count))),
        "rate_mae": float(np.mean(np.abs(actual - expected_rate))),
    }


def audit_frame(frame: pd.DataFrame) -> dict[str, object]:
    frame = frame.sort_values(["draw_no", "candidate_number"]).copy()

    required = {
        "draw_no",
        "candidate_number",
        "selected",
        *(f"freq_w{window}" for window in WINDOWS),
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    selected_matrix = (
        frame.pivot(
            index="draw_no",
            columns="candidate_number",
            values="selected",
        )
        .sort_index()
        .sort_index(axis=1)
        .astype(float)
    )

    records: list[dict[str, object]] = []

    for window in WINDOWS:
        prior_count = (
            selected_matrix.shift(1)
            .rolling(window=window, min_periods=1)
            .sum()
            .fillna(0.0)
        )

        prior_observation_count = np.minimum(
            np.arange(len(selected_matrix), dtype=float),
            float(window),
        )
        denominators = np.maximum(prior_observation_count, 1.0)
        prior_rate = prior_count.div(denominators, axis=0)

        actual = (
            frame.pivot(
                index="draw_no",
                columns="candidate_number",
                values=f"freq_w{window}",
            )
            .reindex_like(selected_matrix)
            .astype(float)
        )

        result = compare_column(
            actual.to_numpy().reshape(-1),
            prior_count.to_numpy().reshape(-1),
            prior_rate.to_numpy().reshape(-1),
        )
        records.append(
            {
                "feature": f"freq_w{window}",
                "window": window,
                **result,
            }
        )

    return {
        "rows": int(len(frame)),
        "draws": int(frame["draw_no"].nunique()),
        "candidate_numbers": int(frame["candidate_number"].nunique()),
        "features": records,
        "causality_pass": all(
            max(
                float(record["count_match_rate"]),
                float(record["rate_match_rate"]),
            )
            >= 0.999
            for record in records
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=(
            "runs/data-acquisition-loto7/features/"
            "candidate_features_v2.parquet"
        ),
    )
    parser.add_argument(
        "--output",
        default="runs/candidate-feature-causality-audit.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    report = audit_frame(pd.read_parquet(input_path))
    report["input"] = str(input_path.resolve())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for record in report["features"]:
        print(
            f"{record['feature']}: "
            f"best={record['best_convention']} "
            f"count_match={record['count_match_rate']:.6f} "
            f"rate_match={record['rate_match_rate']:.6f}"
        )

    print(f"CAUSALITY_PASS={report['causality_pass']}")
    print(f"OUTPUT={output_path.resolve()}")

    if not report["causality_pass"]:
        raise SystemExit(
            "Candidate frequency features failed the strict causality audit."
        )


if __name__ == "__main__":
    main()
