from __future__ import annotations

import argparse
import hashlib
import json
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_seed_files(campaign: Path) -> list[Path]:
    files = sorted(campaign.glob("seed-*/ablation_results.csv"))
    if not files:
        raise ValueError(f"no seed result files found under {campaign}")
    return files


def validate_seed_frame(
    frame: pd.DataFrame,
    *,
    source: Path,
) -> dict[str, object]:
    required = {
        "model_id",
        "fold",
        "seed",
        "condition",
        "feature_group",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{source}: missing required columns {sorted(missing)}")

    models = sorted(frame["model_id"].dropna().astype(str).unique())
    folds = sorted(frame["fold"].dropna().unique())
    seeds = sorted(frame["seed"].dropna().unique())

    if len(seeds) != 1:
        raise ValueError(f"{source}: expected exactly one seed, got {seeds}")

    condition_rows = (
        frame[
            [
                "condition",
                "feature_group",
            ]
        ]
        .drop_duplicates()
        .sort_values(["condition", "feature_group"])
    )
    condition_count = len(condition_rows)

    expected_rows = len(models) * len(folds) * condition_count
    if len(frame) != expected_rows:
        raise ValueError(
            f"{source}: expected {expected_rows} rows "
            f"({len(models)} models × {len(folds)} folds × "
            f"{condition_count} condition/group pairs), got {len(frame)}"
        )

    duplicates = frame.duplicated(
        ["model_id", "fold", "seed", "condition", "feature_group"],
        keep=False,
    )
    if duplicates.any():
        raise ValueError(f"{source}: duplicate model/fold/seed/condition/group rows")

    return {
        "source": str(source.resolve()),
        "sha256": _sha256(source),
        "seed": int(seeds[0]),
        "rows": int(len(frame)),
        "models": models,
        "fold_count": int(len(folds)),
        "condition_group_count": int(condition_count),
        "expected_rows": int(expected_rows),
    }


def load_campaign(
    campaign: Path,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    frames: list[pd.DataFrame] = []
    manifests: list[dict[str, object]] = []

    for path in discover_seed_files(campaign):
        frame = pd.read_csv(path)
        manifests.append(validate_seed_frame(frame, source=path))
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)

    duplicates = combined.duplicated(
        ["model_id", "fold", "seed", "condition", "feature_group"],
        keep=False,
    )
    if duplicates.any():
        raise ValueError("combined campaign contains duplicate rows")

    return combined, manifests


def _cluster_bootstrap_by_fold(
    fold_values: pd.Series,
    *,
    iterations: int,
    seed: int,
) -> tuple[float, float, float]:
    values = fold_values.to_numpy(dtype=float)
    values = values[np.isfinite(values)]

    if values.size == 0:
        return np.nan, np.nan, np.nan

    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, values.size, size=(iterations, values.size))
    estimates = values[indexes].mean(axis=1)
    low, median, high = np.quantile(estimates, [0.025, 0.5, 0.975])
    return float(low), float(median), float(high)


def _contribution(
    full_values: np.ndarray,
    comparison_values: np.ndarray,
    *,
    metric: str,
) -> np.ndarray:
    if metric in LOWER_IS_BETTER:
        return comparison_values - full_values
    if metric in HIGHER_IS_BETTER:
        return full_values - comparison_values
    raise ValueError(f"unsupported metric: {metric}")


def aggregate_multiseed(
    frame: pd.DataFrame,
    *,
    bootstrap_iterations: int = 20_000,
    bootstrap_seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["model_id", "fold", "seed"]

    full = frame[frame["condition"].eq("full_exogenous")].copy()
    dropped = frame[frame["condition"].eq("drop_group")].copy()

    if full.empty:
        raise ValueError("no full_exogenous rows")
    if dropped.empty:
        raise ValueError("no drop_group rows")

    metrics = [column for column in frame.columns if column in LOWER_IS_BETTER | HIGHER_IS_BETTER]
    if not metrics:
        raise ValueError("no supported metric columns")

    result_records: list[dict[str, object]] = []
    seed_records: list[dict[str, object]] = []

    for feature_group, group_frame in dropped.groupby(
        "feature_group",
        sort=True,
    ):
        paired = group_frame.merge(
            full,
            on=keys,
            suffixes=("_comparison", "_full"),
            validate="one_to_one",
        )

        for model_id, model_frame in paired.groupby(
            "model_id",
            sort=True,
        ):
            for metric in metrics:
                full_values = model_frame[f"{metric}_full"].to_numpy(dtype=float)
                comparison_values = model_frame[f"{metric}_comparison"].to_numpy(dtype=float)

                contributions = _contribution(
                    full_values,
                    comparison_values,
                    metric=metric,
                )

                detail = model_frame[["fold", "seed"]].copy()
                detail["contribution"] = contributions

                fold_mean = detail.groupby("fold")["contribution"].mean()
                seed_mean = detail.groupby("seed")["contribution"].mean()

                ci_low, ci_median, ci_high = _cluster_bootstrap_by_fold(
                    fold_mean,
                    iterations=bootstrap_iterations,
                    seed=bootstrap_seed,
                )

                midpoint = len(fold_mean) // 2
                ordered_fold_values = fold_mean.sort_index().to_numpy(dtype=float)
                front = ordered_fold_values[:midpoint]
                back = ordered_fold_values[midpoint:]

                result_records.append(
                    {
                        "model_id": model_id,
                        "feature_group": feature_group,
                        "metric": metric,
                        "paired_rows": int(len(model_frame)),
                        "unique_folds": int(detail["fold"].nunique()),
                        "unique_seeds": int(detail["seed"].nunique()),
                        "full_mean": float(np.mean(full_values)),
                        "comparison_mean": float(np.mean(comparison_values)),
                        "absolute_contribution": float(np.mean(contributions)),
                        "cluster_ci95_low": ci_low,
                        "cluster_ci95_median": ci_median,
                        "cluster_ci95_high": ci_high,
                        "positive_fold_rate": float(np.mean(fold_mean > 0)),
                        "positive_seed_rate": float(np.mean(seed_mean > 0)),
                        "all_seeds_positive": bool(np.all(seed_mean > 0)),
                        "seed_min_contribution": float(seed_mean.min()),
                        "seed_max_contribution": float(seed_mean.max()),
                        "seed_std_contribution": (
                            float(seed_mean.std(ddof=1)) if len(seed_mean) > 1 else 0.0
                        ),
                        "front_half_contribution": (
                            float(np.mean(front)) if front.size else np.nan
                        ),
                        "back_half_contribution": (float(np.mean(back)) if back.size else np.nan),
                    }
                )

                for seed_value, contribution_value in seed_mean.items():
                    seed_records.append(
                        {
                            "model_id": model_id,
                            "feature_group": feature_group,
                            "metric": metric,
                            "seed": int(seed_value),
                            "seed_contribution": float(contribution_value),
                        }
                    )

    result = pd.DataFrame(result_records)
    seed_result = pd.DataFrame(seed_records)

    result["stable_across_seeds"] = (
        result["unique_seeds"].ge(3)
        & result["cluster_ci95_low"].gt(0)
        & result["positive_fold_rate"].ge(0.60)
        & result["all_seeds_positive"]
        & result["front_half_contribution"].gt(0)
        & result["back_half_contribution"].gt(0)
    )

    result = result.sort_values(
        [
            "stable_across_seeds",
            "metric",
            "absolute_contribution",
        ],
        ascending=[False, True, False],
        ignore_index=True,
    )

    return result, seed_result


def write_outputs(
    *,
    campaign: Path,
    output_dir: Path,
    combined: pd.DataFrame,
    source_manifests: list[dict[str, object]],
    summary: pd.DataFrame,
    seed_summary: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_csv = output_dir / "combined_ablation_results.csv"
    combined_parquet = output_dir / "combined_ablation_results.parquet"
    summary_csv = output_dir / "multiseed_contribution_summary.csv"
    seed_csv = output_dir / "seed_contribution_detail.csv"
    stable_csv = output_dir / "stable_across_all_seeds.csv"
    manifest_json = output_dir / "multiseed_manifest.json"

    combined.to_csv(combined_csv, index=False)

    parquet_written = True
    parquet_error = None
    try:
        combined.to_parquet(combined_parquet, index=False)
    except (ImportError, ModuleNotFoundError) as exc:
        parquet_written = False
        parquet_error = f"{type(exc).__name__}: {exc}"
        if combined_parquet.exists():
            combined_parquet.unlink()

    summary.to_csv(summary_csv, index=False)
    seed_summary.to_csv(seed_csv, index=False)
    summary[summary["stable_across_seeds"]].to_csv(
        stable_csv,
        index=False,
    )

    manifest = {
        "schema_version": 1,
        "campaign": str(campaign.resolve()),
        "source_files": source_manifests,
        "combined_rows": int(len(combined)),
        "models": sorted(combined["model_id"].dropna().astype(str).unique()),
        "seeds": sorted(int(value) for value in combined["seed"].dropna().unique()),
        "fold_count": int(combined["fold"].nunique()),
        "condition_group_pairs": (
            combined[["condition", "feature_group"]]
            .drop_duplicates()
            .sort_values(["condition", "feature_group"])
            .to_dict(orient="records")
        ),
        "outputs": {
            "combined_csv": {
                "path": str(combined_csv.resolve()),
                "sha256": _sha256(combined_csv),
            },
            "combined_parquet": {
                "path": (str(combined_parquet.resolve()) if parquet_written else None),
                "sha256": (_sha256(combined_parquet) if parquet_written else None),
                "written": parquet_written,
                "error": parquet_error,
            },
            "summary_csv": {
                "path": str(summary_csv.resolve()),
                "sha256": _sha256(summary_csv),
            },
            "seed_csv": {
                "path": str(seed_csv.resolve()),
                "sha256": _sha256(seed_csv),
            },
            "stable_csv": {
                "path": str(stable_csv.resolve()),
                "sha256": _sha256(stable_csv),
            },
        },
    }
    manifest_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"COMBINED_ROWS={len(combined)}")
    print(f"SUMMARY_ROWS={len(summary)}")
    print(f"STABLE_ROWS={int(summary['stable_across_seeds'].sum())}")
    print(f"OUTPUT_DIR={output_dir.resolve()}")
    print(f"MANIFEST={manifest_json.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=20_000,
    )
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    args = parser.parse_args()

    campaign = Path(args.campaign)
    output_dir = Path(args.output_dir or campaign / "multiseed_analysis")

    combined, manifests = load_campaign(campaign)
    summary, seed_summary = aggregate_multiseed(
        combined,
        bootstrap_iterations=args.bootstrap_iterations,
        bootstrap_seed=args.bootstrap_seed,
    )
    write_outputs(
        campaign=campaign,
        output_dir=output_dir,
        combined=combined,
        source_manifests=manifests,
        summary=summary,
        seed_summary=seed_summary,
    )


if __name__ == "__main__":
    main()
