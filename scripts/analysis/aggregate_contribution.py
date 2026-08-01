from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


LOWER_IS_BETTER = {
    "position_mae",
    "position_mse",
    "brier",
    "log_loss",
}

HIGHER_IS_BETTER = {
    "element_within_1",
    "row_within_1",
    "mean_hits_at_7",
    "brier_skill_score",
}


def paired_bootstrap(
    values: np.ndarray,
    *,
    iterations: int = 20_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if values.size == 0:
        return np.nan, np.nan, np.nan

    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, values.size, size=(iterations, values.size))
    estimates = values[indexes].mean(axis=1)
    low, median, high = np.quantile(estimates, [0.025, 0.5, 0.975])
    return float(low), float(median), float(high)


def safe_relative_mean(values: np.ndarray) -> tuple[float | None, int]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None, 0
    return float(finite.mean() * 100.0), int(finite.size)


def aggregate_contributions(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"model_id", "fold", "seed", "condition", "feature_group"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    keys = ["model_id", "fold", "seed"]

    full = frame[frame["condition"].eq("full_exogenous")].copy()
    ablated = frame[frame["condition"].eq("drop_group")].copy()

    if full.empty:
        raise ValueError("no full_exogenous rows")
    if ablated.empty:
        raise ValueError("no drop_group rows")

    duplicate_full = full.duplicated(keys, keep=False)
    if duplicate_full.any():
        raise ValueError("full_exogenous rows are not unique by model_id/fold/seed")

    metrics = [
        column
        for column in frame.columns
        if column in LOWER_IS_BETTER | HIGHER_IS_BETTER
    ]
    if not metrics:
        raise ValueError("no supported metric columns")

    records: list[dict[str, object]] = []

    for group_name, group_frame in ablated.groupby("feature_group", sort=True):
        duplicate_group = group_frame.duplicated(keys, keep=False)
        if duplicate_group.any():
            raise ValueError(
                f"drop_group rows for {group_name!r} are not unique by model_id/fold/seed"
            )

        paired = group_frame.merge(
            full,
            on=keys,
            suffixes=("_ablated", "_full"),
            how="inner",
            validate="one_to_one",
        )

        for model_id, model_frame in paired.groupby("model_id", sort=True):
            for metric in metrics:
                full_values = model_frame[f"{metric}_full"].to_numpy(dtype=float)
                ablated_values = model_frame[f"{metric}_ablated"].to_numpy(dtype=float)

                if metric in LOWER_IS_BETTER:
                    absolute = ablated_values - full_values
                else:
                    absolute = full_values - ablated_values

                relative = np.divide(
                    absolute,
                    np.abs(ablated_values),
                    out=np.full_like(absolute, np.nan, dtype=float),
                    where=np.abs(ablated_values) > 1e-12,
                )

                relative_pct, relative_rows = safe_relative_mean(relative)
                ci_low, ci_median, ci_high = paired_bootstrap(absolute)

                midpoint = len(model_frame) // 2
                first_half = absolute[:midpoint] if midpoint else np.array([], dtype=float)
                second_half = absolute[midpoint:]

                records.append(
                    {
                        "model_id": model_id,
                        "feature_group": group_name,
                        "metric": metric,
                        "paired_rows": int(len(model_frame)),
                        "full_mean": float(np.mean(full_values)),
                        "ablated_mean": float(np.mean(ablated_values)),
                        "absolute_contribution": float(np.mean(absolute)),
                        "relative_contribution_pct": relative_pct,
                        "relative_contribution_defined_rows": relative_rows,
                        "zero_baseline_rows": int(
                            np.sum(np.abs(ablated_values) <= 1e-12)
                        ),
                        "ci95_low": ci_low,
                        "ci95_median": ci_median,
                        "ci95_high": ci_high,
                        "positive_fold_rate": float(np.mean(absolute > 0)),
                        "front_half_contribution": (
                            float(np.mean(first_half)) if first_half.size else np.nan
                        ),
                        "back_half_contribution": (
                            float(np.mean(second_half)) if second_half.size else np.nan
                        ),
                    }
                )

    return pd.DataFrame(records).sort_values(
        ["metric", "absolute_contribution", "model_id", "feature_group"],
        ascending=[True, False, True, True],
        ignore_index=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(input_path)
    result = aggregate_contributions(frame)

    csv_path = output_dir / "contribution_summary.csv"
    result.to_csv(csv_path, index=False)

    stable = result[
        (result["paired_rows"] >= 30)
        & (result["ci95_low"] > 0)
        & (result["positive_fold_rate"] >= 0.60)
        & (result["front_half_contribution"] > 0)
        & (result["back_half_contribution"] > 0)
    ].copy()

    stable_path = output_dir / "stable_positive_contributions.csv"
    stable.to_csv(stable_path, index=False)

    print(f"SUMMARY={csv_path.resolve()}")
    print(f"STABLE={stable_path.resolve()}")
    print(f"ROWS={len(result)}")
    print(f"STABLE_ROWS={len(stable)}")


if __name__ == "__main__":
    main()
