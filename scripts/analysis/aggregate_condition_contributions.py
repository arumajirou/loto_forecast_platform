from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from loto.analysis.contribution import Comparison, paired_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=5000)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.input)
    required = {"model_id", "fold", "seed", "condition", "feature_group"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.duplicated(["model_id", "fold", "seed", "condition", "feature_group"]).any():
        raise ValueError("duplicate comparison rows")
    metric_columns = [column for column in ("brier", "log_loss", "position_mae", "position_mse", "mean_hits_at_7", "element_within_1", "row_within_1") if column in frame]
    if not metric_columns:
        raise ValueError("no supported metric columns")
    comparisons = [
        ("condition_contribution_summary.csv", Comparison("drop_group", "full_exogenous", "drop_group")),
        ("add_one_group_summary.csv", Comparison("add_group", "full_exogenous", "add_group")),
        ("permutation_contribution_summary.csv", Comparison("permutation", "full_exogenous", "group_permutation")),
    ]
    written: list[str] = []
    stable_frames: list[pd.DataFrame] = []
    for filename, comparison in comparisons:
        outputs = []
        for metric in metric_columns:
            try:
                outputs.append(paired_summary(frame, comparison=comparison, metric=metric, bootstrap_iterations=args.bootstrap_iterations))
            except ValueError:
                continue
        result = pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()
        result.to_csv(args.output_dir / filename, index=False)
        written.append(filename)
        if not result.empty:
            stable_frames.append(result[(result["cluster_ci95_low"] > 0) & result["all_seeds_positive"] & (result["positive_fold_rate"] >= 0.6) & (result["front_half_contribution"] > 0) & (result["back_half_contribution"] > 0) & (result["pvalue_holm"] < 0.05)].copy())
    quality_columns = [column for column in ("probability_std", "probability_unique_count", "probability_quality_pass") if column in frame]
    quality = frame.groupby(["model_id", "condition", "feature_group"], dropna=False)[quality_columns].agg(["mean", "min", "max"]).reset_index() if quality_columns else pd.DataFrame()
    quality.to_csv(args.output_dir / "probability_quality_summary.csv", index=False)
    written.append("probability_quality_summary.csv")
    stable = pd.concat(stable_frames, ignore_index=True) if stable_frames else pd.DataFrame()
    stable.to_csv(args.output_dir / "stable_contributions.csv", index=False)
    written.append("stable_contributions.csv")
    manifest = {
        "schema_version": "2.2",
        "input": str(args.input.resolve()),
        "input_sha256": sha256(args.input),
        "rows": len(frame),
        "models": sorted(frame["model_id"].astype(str).unique()),
        "folds": int(frame["fold"].nunique()),
        "seeds": sorted(int(value) for value in frame["seed"].unique()),
        "outputs": written,
        "no_model_beats_baseline": bool(stable.empty),
    }
    (args.output_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
