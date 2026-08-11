#!/usr/bin/env python
"""Run the six-game development-only statistical campaign.

This is the reproducible, repository-owned form of the manually verified campaign. It keeps
the trailing holdout physically outside every statistical calculation, evaluates all 33 raw
position/digit series, adds unique within-draw pairwise associations, and applies canonical
Holm/BH correction at temporal, association, and omnibus family levels.

The association layer is descriptive only. In particular, lotto/bingo ``n1..nK`` columns are
sorted order statistics, so their contemporaneous correlations are structurally induced and
must not be interpreted as predictive or causal evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.analysis.dependence import ljung_box_test, pearson_association, spearman_association
from loto.analysis.multiple_testing import adjust_hypotheses
from loto.analysis.trends import linear_trend, mean_shift_scan
from loto.data.lineage import frame_fingerprint
from loto.evaluation.splits import split_development_holdout

GAME_COLUMNS: dict[str, tuple[str, ...]] = {
    "mini": ("n1", "n2", "n3", "n4", "n5"),
    "loto6": ("n1", "n2", "n3", "n4", "n5", "n6"),
    "loto7": ("n1", "n2", "n3", "n4", "n5", "n6", "n7"),
    "bingo5": ("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
    "numbers3": ("d1", "d2", "d3"),
    "numbers4": ("d1", "d2", "d3", "d4"),
}

SORTED_POSITION_GAMES = frozenset({"mini", "loto6", "loto7", "bingo5"})
STRUCTURAL_SORT_WARNING = (
    "sorted position representation induces structural dependence; contemporaneous "
    "association is descriptive and is not predictive or causal evidence"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Six-game development-only trend/dependence/association campaign",
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--holdout-size", type=int, default=50)
    parser.add_argument("--lags", type=int, default=10)
    parser.add_argument("--min-segment", type=int, default=30)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=0.05)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        raise ValueError(f"column not found: {column}")
    values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    if values.ndim != 1 or values.size < 4 or not np.isfinite(values).all():
        raise ValueError(f"column {column!r} must be finite numeric data with >= 4 rows")
    return values


def _validate_chronology(frame: pd.DataFrame, *, game: str) -> None:
    if "draw_date" not in frame.columns:
        raise ValueError(f"{game}: draw_date column is required")
    dates = pd.to_datetime(frame["draw_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError(f"{game}: draw_date must be finite, unique, and monotonically increasing")


def _load_development(
    path: Path,
    *,
    game: str,
    holdout_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    full = pd.read_csv(path)
    _validate_chronology(full, game=game)
    development_slice, holdout_slice = split_development_holdout(len(full), holdout_size)
    development = full.iloc[development_slice].reset_index(drop=True)
    holdout = full.iloc[holdout_slice].reset_index(drop=True)
    if len(holdout) != holdout_size:
        raise RuntimeError(f"{game}: holdout size mismatch")
    metadata = {
        "game": game,
        "path": str(path.resolve()),
        "input_sha256": _sha256(path),
        "input_rows": int(len(full)),
        "development_rows": int(len(development)),
        "holdout_rows": int(len(holdout)),
        "holdout_start_index": int(holdout_slice.start),
        "development_frame_sha256": frame_fingerprint(development),
        "holdout_access": "split_only_not_analyzed",
    }
    return development, holdout, metadata


def _temporal_rows(
    frame: pd.DataFrame,
    *,
    game: str,
    columns: tuple[str, ...],
    lags: int,
    min_segment: int,
    permutations: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in columns:
        values = _numeric(frame, column)
        if lags >= len(values) - 1:
            raise ValueError(f"{game}/{column}: --lags must be smaller than n - 1")

        trend = linear_trend(values)
        serial = ljung_box_test(values, lags)
        change = mean_shift_scan(
            values,
            min_segment=min_segment,
            repetitions=permutations,
            seed=seed,
        )
        representation = "sorted_position" if game in SORTED_POSITION_GAMES else "generic_numeric_series"

        rows.extend(
            [
                {
                    "hypothesis_id": f"temporal::{game}::{column}::linear_trend",
                    "family": "temporal",
                    "game": game,
                    "series": column,
                    "test": "linear_trend",
                    "representation": representation,
                    "statistic": trend.slope,
                    "effect": trend.r_value,
                    "raw_p_value": trend.p_value,
                    "n": trend.n,
                    "causal_claim_eligible": False,
                },
                {
                    "hypothesis_id": f"temporal::{game}::{column}::ljung_box_lags_{lags}",
                    "family": "temporal",
                    "game": game,
                    "series": column,
                    "test": "ljung_box",
                    "representation": representation,
                    "statistic": serial.statistic,
                    "effect": max((abs(value) for value in serial.autocorrelations), default=0.0),
                    "raw_p_value": serial.p_value,
                    "n": serial.n,
                    "causal_claim_eligible": False,
                },
                {
                    "hypothesis_id": f"temporal::{game}::{column}::max_mean_shift",
                    "family": "temporal",
                    "game": game,
                    "series": column,
                    "test": "max_mean_shift",
                    "representation": representation,
                    "statistic": change.absolute_mean_shift,
                    "effect": change.standardized_effect,
                    "raw_p_value": change.permutation_p_value,
                    "n": change.n,
                    "causal_claim_eligible": False,
                },
            ]
        )
    return rows


def _association_rows(
    frame: pd.DataFrame,
    *,
    game: str,
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    representation = "sorted_position" if game in SORTED_POSITION_GAMES else "generic_numeric_series"
    warning = STRUCTURAL_SORT_WARNING if game in SORTED_POSITION_GAMES else None

    for left, right in itertools.combinations(columns, 2):
        left_values = _numeric(frame, left)
        right_values = _numeric(frame, right)
        pearson = pearson_association(left_values, right_values, representation=representation)
        spearman = spearman_association(left_values, right_values, representation=representation)

        for result in (pearson, spearman):
            rows.append(
                {
                    "hypothesis_id": f"association::{game}::{left}::{right}::{result.method}",
                    "family": "association",
                    "game": game,
                    "left_series": left,
                    "right_series": right,
                    "test": result.method,
                    "representation": result.representation,
                    "statistic": result.statistic,
                    "effect": result.statistic,
                    "raw_p_value": result.p_value,
                    "n": result.n,
                    "structural_warning": warning,
                    "causal_claim_eligible": False,
                }
            )
    return rows


def _correction_rows(
    records: list[dict[str, Any]],
    *,
    family: str,
    alpha: float,
) -> list[dict[str, Any]]:
    ids = [str(row["hypothesis_id"]) for row in records]
    p_values = [float(row["raw_p_value"]) for row in records]
    holm = adjust_hypotheses(ids, p_values, method="holm", alpha=alpha)
    bh = adjust_hypotheses(ids, p_values, method="benjamini_hochberg", alpha=alpha)
    return [
        {
            "family": family,
            "hypothesis_id": source["hypothesis_id"],
            "raw_p_value": source["raw_p_value"],
            "holm_adjusted_p": h.adjusted_p_value,
            "holm_rejected": h.rejected,
            "bh_adjusted_p": b.adjusted_p_value,
            "bh_rejected": b.rejected,
        }
        for source, h, b in zip(records, holm, bh, strict=True)
    ]


def _write_sha256s(output: Path) -> None:
    rows = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{_sha256(path)}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.holdout_size <= 0:
        raise ValueError("--holdout-size must be positive")
    if not 0.0 < args.alpha < 1.0:
        raise ValueError("--alpha must be in (0, 1)")

    data_root = Path(args.data_root).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse output directory: {output}")
    output.mkdir(parents=True)

    dataset_manifest: list[dict[str, Any]] = []
    temporal: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []

    for game, columns in GAME_COLUMNS.items():
        source = data_root / game / "normalized" / f"{game}.csv"
        development, _holdout, metadata = _load_development(
            source,
            game=game,
            holdout_size=args.holdout_size,
        )
        dataset_manifest.append(metadata)
        temporal.extend(
            _temporal_rows(
                development,
                game=game,
                columns=columns,
                lags=args.lags,
                min_segment=args.min_segment,
                permutations=args.permutations,
                seed=args.seed,
            )
        )
        associations.extend(_association_rows(development, game=game, columns=columns))

    expected_positions = sum(len(columns) for columns in GAME_COLUMNS.values())
    expected_pairs = sum(len(tuple(itertools.combinations(columns, 2))) for columns in GAME_COLUMNS.values())
    if expected_positions != 33 or len(temporal) != 99:
        raise RuntimeError("unexpected temporal campaign cardinality")
    if expected_pairs != 83 or len(associations) != 166:
        raise RuntimeError("unexpected association campaign cardinality")

    omnibus = [*temporal, *associations]
    temporal_correction = _correction_rows(temporal, family="temporal", alpha=args.alpha)
    association_correction = _correction_rows(
        associations,
        family="association",
        alpha=args.alpha,
    )
    omnibus_correction = _correction_rows(omnibus, family="omnibus", alpha=args.alpha)

    config_payload = {
        "schema_version": "1.0.0",
        "data_root": str(data_root),
        "holdout_size_per_game": args.holdout_size,
        "lags": args.lags,
        "min_segment": args.min_segment,
        "permutations": args.permutations,
        "seed": args.seed,
        "alpha": args.alpha,
        "games": list(GAME_COLUMNS),
        "position_series": expected_positions,
        "association_pairs": expected_pairs,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "causal_claim": False,
    }
    run_hash = hashlib.sha256(
        json.dumps(config_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    config_payload["run_id"] = f"six-game-development-science-{run_hash}"

    summary = {
        "schema_version": "1.0.0",
        "run_id": config_payload["run_id"],
        "status": "SUCCEEDED",
        "games": 6,
        "position_series": expected_positions,
        "temporal_hypotheses": len(temporal),
        "association_pairs": expected_pairs,
        "association_hypotheses": len(associations),
        "omnibus_hypotheses": len(omnibus),
        "holdout_size_per_game": args.holdout_size,
        "temporal_holm_rejections": sum(row["holm_rejected"] for row in temporal_correction),
        "temporal_bh_rejections": sum(row["bh_rejected"] for row in temporal_correction),
        "association_holm_rejections": sum(
            row["holm_rejected"] for row in association_correction
        ),
        "association_bh_rejections": sum(row["bh_rejected"] for row in association_correction),
        "omnibus_holm_rejections": sum(row["holm_rejected"] for row in omnibus_correction),
        "omnibus_bh_rejections": sum(row["bh_rejected"] for row in omnibus_correction),
        "sorted_position_association_warning": STRUCTURAL_SORT_WARNING,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "causal_claim": False,
    }

    _write_json(output / "CONFIG.json", config_payload)
    _write_json(output / "DATASET_MANIFEST.json", dataset_manifest)
    _write_json(output / "TEMPORAL_TESTS.json", temporal)
    _write_csv(output / "TEMPORAL_TESTS.csv", temporal)
    _write_json(output / "ASSOCIATION_TESTS.json", associations)
    _write_csv(output / "ASSOCIATION_TESTS.csv", associations)
    _write_json(output / "MULTIPLICITY_TEMPORAL.json", temporal_correction)
    _write_json(output / "MULTIPLICITY_ASSOCIATION.json", association_correction)
    _write_json(output / "MULTIPLICITY_OMNIBUS.json", omnibus_correction)
    _write_json(output / "CAMPAIGN_SUMMARY.json", summary)
    _write_sha256s(output)

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
