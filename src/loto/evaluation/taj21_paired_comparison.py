"""Paired Hit@±1 inference for TAJ-21 development-only OOF results."""

from __future__ import annotations

from typing import Any

import numpy as np

from loto.evaluation.multiplicity import correct, paired_bootstrap_p

REFERENCE_BASELINE_ID = "baseline:statistical_ar1"
PAIRING_UNIT = "seed_fold_hit_at_1"


def _units(row: dict[str, Any]) -> dict[tuple[int, int], float]:
    units: dict[tuple[int, int], float] = {}
    for seed_result in row.get("seed_results", []):
        seed = int(seed_result["seed"])
        for fold in seed_result.get("fold_metrics", []):
            key = (seed, int(fold["fold_id"]))
            if key in units:
                raise ValueError(f"duplicate paired unit: {row.get('candidate_id')} {key}")
            units[key] = float(fold["metrics"]["hit_at_1"])
    return units


def build_paired_comparisons(
    results: list[dict[str, Any]],
    games: tuple[str, ...],
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Compare every successful candidate to pre-specified statistical AR(1).

    The inference unit is one identical seed/fold OOF block. Candidate and baseline therefore
    use exactly the same OOF targets in every paired unit. Holm correction is applied within
    each game across all valid candidate hypotheses.
    """

    comparisons: list[dict[str, Any]] = []
    for game in games:
        game_rows = [row for row in results if row["game"] == game]
        baseline = next(
            (row for row in game_rows if row["candidate_id"] == REFERENCE_BASELINE_ID),
            None,
        )
        if baseline is None or baseline["status"] != "SUCCEEDED":
            raise ValueError(f"reference baseline is not successful for {game}")
        baseline_units = _units(baseline)
        valid_indexes: list[int] = []
        raw_p: list[float] = []

        for row in game_rows:
            if row["source"] not in {"catalog", "probabilistic"}:
                continue
            item: dict[str, Any] = {
                "game": game,
                "candidate_id": row["candidate_id"],
                "candidate_status": row["status"],
                "reference_baseline": REFERENCE_BASELINE_ID,
                "metric": "hit_at_1",
                "pairing_unit": PAIRING_UNIT,
                "comparison_status": "NOT_APPLICABLE_CANDIDATE_NOT_SUCCEEDED",
                "n_pairs": 0,
                "raw_p_value": None,
                "holm_adjusted_p_value": None,
                "rejected_at_alpha": None,
                "candidate_minus_baseline_hit_at_1": None,
                "ci_low": None,
                "ci_high": None,
            }
            comparisons.append(item)
            if row["status"] != "SUCCEEDED":
                continue

            candidate_units = _units(row)
            if set(candidate_units) != set(baseline_units):
                raise ValueError(f"paired OOF units do not align for {game}/{row['candidate_id']}")
            keys = sorted(candidate_units)
            candidate_hit = np.asarray([candidate_units[key] for key in keys], dtype=float)
            baseline_hit = np.asarray([baseline_units[key] for key in keys], dtype=float)
            paired = paired_bootstrap_p(
                1.0 - candidate_hit,
                1.0 - baseline_hit,
                n_boot=n_boot,
                seed=42,
                alternative="less",
            )
            item.update(
                {
                    "comparison_status": "VALID",
                    "n_pairs": int(paired["n"]),
                    "raw_p_value": float(paired["p_value"]),
                    "candidate_minus_baseline_hit_at_1": float(
                        np.mean(candidate_hit - baseline_hit)
                    ),
                    "ci_low": float(-paired["ci_high"]),
                    "ci_high": float(-paired["ci_low"]),
                }
            )
            valid_indexes.append(len(comparisons) - 1)
            raw_p.append(float(paired["p_value"]))

        correction = correct(raw_p, method="holm", alpha=alpha)
        for local_index, comparison_index in enumerate(valid_indexes):
            comparisons[comparison_index]["holm_adjusted_p_value"] = float(
                correction.adjusted_p[local_index]
            )
            comparisons[comparison_index]["rejected_at_alpha"] = bool(
                correction.rejected[local_index]
            )

    return {
        "schema_version": "taj21-paired-comparisons-v1",
        "reference_baseline": REFERENCE_BASELINE_ID,
        "metric": "hit_at_1",
        "pairing_unit": PAIRING_UNIT,
        "bootstrap_repetitions": n_boot,
        "multiplicity_correction": "holm",
        "alpha": alpha,
        "comparisons": comparisons,
    }
