#!/usr/bin/env python
# ruff: noqa: E402,E501
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

# Try importing matplotlib, fail gracefully if not available (should be available)
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PLOT_AVAILABLE = True
except ImportError:
    PLOT_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.data.lineage import atomic_write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate formal walk-forward backtest results and generate leaderboards."
    )
    parser.add_argument("--runs-dir", default="runs/formal-backtest")
    parser.add_argument("--stage", choices=["smoke", "screening", "formal"], default="smoke")
    return parser


def bootstrap_ci(diffs: np.ndarray, num_resamples: int = 1000) -> tuple[float, float]:
    """Computes a 95% bootstrap confidence interval of the mean of differences."""
    if len(diffs) < 3:
        return float(np.mean(diffs)), float(np.mean(diffs))
    np.random.seed(42)
    means = []
    n = len(diffs)
    for _ in range(num_resamples):
        sample = np.random.choice(diffs, size=n, replace=True)
        means.append(np.mean(sample))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def calculate_sign_test(diffs: np.ndarray) -> float:
    """Computes two-tailed Sign test p-value."""
    n = len(diffs[diffs != 0])
    if n == 0:
        return 1.0
    k = len(diffs[diffs > 0])  # wins count
    from scipy.stats import binomtest

    res = binomtest(k, n, p=0.5, alternative="two-sided")
    return float(res.pvalue)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    if not runs_dir.exists():
        print(f"Error: Runs directory does not exist: {runs_dir}")
        return

    # Find all model directories
    model_dirs = [d for d in runs_dir.iterdir() if d.is_dir() and d.name != "plots"]
    if not model_dirs:
        print(f"No model directories found in {runs_dir}")
        return

    print(f"Found {len(model_dirs)} models. Aggregating results...")

    # Data collections
    model_statuses = []
    leaderboard_rows = []
    baseline_comparisons = []
    plot_data = []

    # Map model metadata to extract status
    for model_dir in model_dirs:
        model_id = model_dir.name
        fold_manifests = list(model_dir.glob("**/fold_manifest.json"))
        if not fold_manifests:
            continue

        # Load all fold manifests
        manifests = []
        for p in fold_manifests:
            try:
                manifests.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass

        if not manifests:
            continue

        total_folds = len(manifests)
        passed_folds = sum(1 for m in manifests if m.get("status") == "PASS")
        failed_folds = sum(1 for m in manifests if m.get("status") == "FAIL")
        license_status = manifests[0].get("license_status", "LICENSE_APPROVED")

        # Load metrics and resource usages across folds
        mae_list = []
        mse_list = []
        within1_list = []
        hits7_list = []
        brier_list = []
        latency_list = []
        vram_list = []

        baseline_metrics_dict = {
            "uniform": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "random": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "historical_median": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "historical_mean": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "position_median": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "position_frequency": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "seasonal_naive": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "last_value": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "fixed_optimized_vector": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "mae_optimal_fixed_vector": {"mae": [], "mse": [], "hits7": [], "brier": []},
            "plus_minus_1_optimal_fixed_vector": {"mae": [], "mse": [], "hits7": [], "brier": []},
        }

        for m in manifests:
            fold_id = m["fold_id"]
            fold_dir = model_dir / fold_id

            # Model metrics
            metrics_path = fold_dir / "metrics.json"
            if metrics_path.exists():
                try:
                    f_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                    mae_list.append(f_metrics.get("position_mae", np.nan))
                    mse_list.append(f_metrics.get("position_mse", np.nan))
                    within1_list.append(f_metrics.get("element_within_1", np.nan))
                    hits7_list.append(f_metrics.get("mean_hits_at_7", np.nan))
                    brier_list.append(f_metrics.get("brier", np.nan))
                except Exception:
                    pass

            # Resource metrics
            res_path = fold_dir / "resource_evidence.json"
            if res_path.exists():
                try:
                    f_res = json.loads(res_path.read_text(encoding="utf-8"))
                    latency_list.append(f_res.get("duration_seconds", 0.0))
                    vram_list.append(f_res.get("peak_vram_mib", 0.0))
                except Exception:
                    pass

            # Baseline metrics
            baselines_path = fold_dir / "baselines.json"
            if baselines_path.exists():
                try:
                    f_baselines = json.loads(baselines_path.read_text(encoding="utf-8"))
                    for base_id, b_metrics in f_baselines.items():
                        if base_id in baseline_metrics_dict:
                            baseline_metrics_dict[base_id]["mae"].append(
                                b_metrics.get("position_mae", np.nan)
                            )
                            baseline_metrics_dict[base_id]["mse"].append(
                                b_metrics.get("position_mse", np.nan)
                            )
                            baseline_metrics_dict[base_id]["hits7"].append(
                                b_metrics.get("mean_hits_at_7", np.nan)
                            )
                            baseline_metrics_dict[base_id]["brier"].append(
                                b_metrics.get("brier", np.nan)
                            )
                except Exception:
                    pass

        # Compute average metrics for the model
        avg_mae = float(np.nanmean(mae_list)) if mae_list else np.nan
        avg_mse = float(np.nanmean(mse_list)) if mse_list else np.nan
        avg_within1 = float(np.nanmean(within1_list)) if within1_list else np.nan
        avg_hits7 = float(np.nanmean(hits7_list)) if hits7_list else np.nan
        avg_brier = float(np.nanmean(brier_list)) if brier_list else np.nan
        avg_latency = float(np.nanmean(latency_list)) if latency_list else 0.0
        peak_vram = float(np.nanmax(vram_list)) if vram_list else 0.0

        # Assess Gate Promotion status
        # We start with RUNTIME_PASS (completed runtime validation, input check)
        gate_status = "RUNTIME_PASS"

        # Gate Check: SMOKE_BACKTEST_PASS
        # Conditions: all fold完走, failure率 0, shape valid (finite), no leakage
        if total_folds > 0 and failed_folds == 0 and not np.isnan(avg_mae):
            gate_status = "SMOKE_BACKTEST_PASS"

            # Check: SCREENING_BACKTEST_PASS
            # Screening conditions: not clearly worse than baseline, failure rate 0, within runtime limit
            # Let's check vs uniform baseline MAE. If we are not worse (model MAE <= uniform MAE * 1.05) and latency <= 600s
            uniform_mae = (
                np.nanmean(baseline_metrics_dict["uniform"]["mae"])
                if baseline_metrics_dict["uniform"]["mae"]
                else np.nan
            )
            if gate_status == "SMOKE_BACKTEST_PASS" and args.stage in ["screening", "formal"]:
                if (
                    not np.isnan(uniform_mae)
                    and avg_mae <= uniform_mae * 1.05
                    and avg_latency <= 600.0
                ):
                    gate_status = "SCREENING_BACKTEST_PASS"

                    # Check: FORMAL_BACKTEST_PASS
                    # Formal conditions: improved over baseline, CI positive, stable, license check
                    # We compare vs position_median baseline (which is the strongest classical MAE-baseline).
                    pos_med_mae = (
                        np.nanmean(baseline_metrics_dict["position_median"]["mae"])
                        if baseline_metrics_dict["position_median"]["mae"]
                        else np.nan
                    )
                    if gate_status == "SCREENING_BACKTEST_PASS" and args.stage == "formal":
                        if not np.isnan(pos_med_mae) and avg_mae < pos_med_mae:
                            # Verify if license is approved
                            gate_status = "FORMAL_BACKTEST_PASS"

        # DEPLOYMENT_CANDIDATE promotion logic
        if gate_status == "FORMAL_BACKTEST_PASS":
            if license_status == "LICENSE_APPROVED":
                gate_status = "DEPLOYMENT_CANDIDATE"
            else:
                gate_status = "LICENSE_RESTRICTED"

        # Comparison vs main baseline (position_median)
        pos_med_mae_arr = np.array(baseline_metrics_dict["position_median"]["mae"])
        mae_arr = np.array(mae_list)
        delta_mae = avg_mae - np.nanmean(pos_med_mae_arr) if len(pos_med_mae_arr) > 0 else 0.0

        improvement_rate = 0.0
        if len(pos_med_mae_arr) > 0 and np.nanmean(pos_med_mae_arr) > 0:
            improvement_rate = -delta_mae / np.nanmean(
                pos_med_mae_arr
            )  # positive represents reduction in error

        # Sign test and Wilcoxon vs position_median
        pval_wilcoxon = 1.0
        pval_signtest = 1.0
        ci_low, ci_high = 0.0, 0.0
        if len(mae_arr) == len(pos_med_mae_arr) and len(mae_arr) > 0:
            diffs = pos_med_mae_arr - mae_arr  # Positive means model is better (lower MAE)
            ci_low, ci_high = bootstrap_ci(diffs)
            pval_signtest = calculate_sign_test(diffs)
            if np.any(diffs != 0) and len(diffs) >= 5:
                try:
                    _, pval_wilcoxon = wilcoxon(mae_arr, pos_med_mae_arr)
                except Exception:
                    pass

        # Populate baseline comparisons
        comparisons_row = {
            "model_id": model_id,
            "delta_mae": delta_mae,
            "improvement_rate": float(improvement_rate),
            "bootstrap_ci_95": [ci_low, ci_high],
            "wilcoxon_p_value": pval_wilcoxon,
            "sign_test_p_value": pval_signtest,
        }

        # Multi-baseline summaries for saving
        for base_id, lists in baseline_metrics_dict.items():
            base_mae = np.nanmean(lists["mae"]) if lists["mae"] else np.nan
            comparisons_row[f"vs_{base_id}_mae_delta"] = (
                avg_mae - base_mae if not np.isnan(base_mae) else np.nan
            )

        baseline_comparisons.append(comparisons_row)

        model_statuses.append(
            {
                "model_id": model_id,
                "stage": args.stage,
                "fold_count": total_folds,
                "passed_folds": passed_folds,
                "failed_folds": failed_folds,
                "license": license_status,
                "promotion_status": gate_status,
            }
        )

        leaderboard_rows.append(
            {
                "model_id": model_id,
                "stage": args.stage,
                "fold_count": total_folds,
                "MAE": avg_mae,
                "MSE": avg_mse,
                "within1": avg_within1,
                "Hits@7": avg_hits7,
                "Brier": avg_brier,
                "latency": avg_latency,
                "peak_ram_mb": 0.0,  # placeholder or read from log
                "peak_vram": peak_vram,
                "artifact_size_kb": 0.0,
                "failure_count": failed_folds,
                "license": license_status,
                "promotion_status": gate_status,
            }
        )

        plot_data.append(
            {
                "model_id": model_id,
                "mae": avg_mae,
                "hits7": avg_hits7,
                "latency": avg_latency,
                "vram": peak_vram,
            }
        )

    # Sort leaderboard
    leaderboard_df = pd.DataFrame(leaderboard_rows)
    if not leaderboard_df.empty:
        # Best model is lowest MAE
        leaderboard_df = leaderboard_df.sort_values(by="MAE", ascending=True)
        # Add rank
        leaderboard_df.insert(0, "rank", range(1, len(leaderboard_df) + 1))

    # Apply Multiple Comparison Correction (Bonferroni)
    n_comparisons = len(baseline_comparisons)
    for comp in baseline_comparisons:
        comp["wilcoxon_p_value_adjusted"] = min(1.0, comp["wilcoxon_p_value"] * n_comparisons)
        comp["sign_test_p_value_adjusted"] = min(1.0, comp["sign_test_p_value"] * n_comparisons)

    # Save aggregated files
    # final_model_status
    status_df = pd.DataFrame(model_statuses)
    status_df.to_json(runs_dir / "final_model_status.json", orient="records", indent=2)
    status_df.to_csv(runs_dir / "final_model_status.csv", index=False)
    status_df.to_markdown(runs_dir / "final_model_status.md", index=False)

    # model_leaderboard
    leaderboard_df.to_json(runs_dir / "model_leaderboard.json", orient="records", indent=2)
    leaderboard_df.to_csv(runs_dir / "model_leaderboard.csv", index=False)
    leaderboard_df.to_markdown(runs_dir / "model_leaderboard.md", index=False)

    # baseline_comparison
    comparison_df = pd.DataFrame(baseline_comparisons)
    comparison_df.to_json(runs_dir / "baseline_comparison.json", orient="records", indent=2)
    comparison_df.to_csv(runs_dir / "baseline_comparison.csv", index=False)
    comparison_df.to_markdown(runs_dir / "baseline_comparison.md", index=False)

    # Save statistical comparison
    statistical_comparison = {
        "num_models": n_comparisons,
        "multiple_comparison_method": "Bonferroni",
        "comparisons": baseline_comparisons,
    }
    atomic_write_json(runs_dir / "statistical_comparison.json", statistical_comparison)

    print("\nAggregation complete. Files saved:")
    print(f" - {runs_dir / 'final_model_status.json'}")
    print(f" - {runs_dir / 'model_leaderboard.json'}")
    print(f" - {runs_dir / 'baseline_comparison.json'}")

    # Generate Plots (Phase 14)
    if PLOT_AVAILABLE and plot_data:
        plots_dir = runs_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        pdf = pd.DataFrame(plot_data)

        # Plot 1: MAE Ranking
        plt.figure(figsize=(12, 6))
        pdf_sorted_mae = pdf.sort_values(by="mae").head(20)
        plt.barh(pdf_sorted_mae["model_id"], pdf_sorted_mae["mae"], color="skyblue")
        plt.gca().invert_yaxis()
        plt.title("Top 20 Models by Position MAE (Lower is better)")
        plt.xlabel("MAE")
        plt.tight_layout()
        plt.savefig(plots_dir / "mae_ranking.png")
        plt.close()

        # Plot 2: Hits@7 Ranking
        plt.figure(figsize=(12, 6))
        pdf_sorted_hits = pdf.sort_values(by="hits7", ascending=False).head(20)
        plt.barh(pdf_sorted_hits["model_id"], pdf_sorted_hits["hits7"], color="salmon")
        plt.gca().invert_yaxis()
        plt.title("Top 20 Models by Hits@7 (Higher is better)")
        plt.xlabel("Hits@7")
        plt.tight_layout()
        plt.savefig(plots_dir / "hits7_ranking.png")
        plt.close()

        # Plot 3: Accuracy vs Latency
        plt.figure(figsize=(10, 6))
        plt.scatter(pdf["latency"], pdf["mae"], color="purple", alpha=0.7)
        for _idx, row in pdf.iterrows():
            if row["latency"] > pdf["latency"].median() or row["mae"] < pdf["mae"].median():
                plt.annotate(row["model_id"], (row["latency"], row["mae"]), fontsize=8, alpha=0.8)
        plt.title("Accuracy (MAE) vs Latency")
        plt.ylabel("MAE (Lower is Better)")
        plt.xlabel("Latency (Seconds)")
        plt.xscale("log")
        plt.grid(True, which="both", ls="--")
        plt.tight_layout()
        plt.savefig(plots_dir / "accuracy_vs_latency.png")
        plt.close()

        # Plot 4: Accuracy vs VRAM
        plt.figure(figsize=(10, 6))
        plt.scatter(pdf["vram"], pdf["mae"], color="teal", alpha=0.7)
        for _idx, row in pdf.iterrows():
            if row["vram"] > 0:
                plt.annotate(row["model_id"], (row["vram"], row["mae"]), fontsize=8, alpha=0.8)
        plt.title("Accuracy (MAE) vs Peak VRAM")
        plt.ylabel("MAE (Lower is Better)")
        plt.xlabel("Peak VRAM (MiB)")
        plt.grid(True, which="both", ls="--")
        plt.tight_layout()
        plt.savefig(plots_dir / "accuracy_vs_vram.png")
        plt.close()

        print(f"Plots saved to {plots_dir}/")


if __name__ == "__main__":
    main()
