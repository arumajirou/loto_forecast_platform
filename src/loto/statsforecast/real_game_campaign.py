"""StatsForecast Phase C development campaign over canonical normalized game data.

The runner reuses the existing unified campaign for chronology, rolling folds, baselines,
prediction locking, scoring, and immutable evidence. StatsForecast-specific work is limited
to resolving the already-certified constructor parameters before the existing worker route
is invoked.

The primary development lane evaluates the 39 univariate models. ``SklearnModel`` and
``NaNModel`` remain visible in the 41 x game lane matrix as EXOGENOUS and
EXPECTED_NEGATIVE_CONTROL respectively; they are not silently dropped or mis-scored as
univariate models.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from loto.evaluation import unified_campaign
from loto.evaluation.unified_campaign import UnifiedCampaignConfig
from loto.game.geometry import known_games
from loto.models.catalog_full import ModelEntry

from .certification_io import write_json, write_manifest_and_sums
from .real_game_preflight import statsforecast_entries
from .real_game_runtime import RealGameLane, lane_for_model, resolve_entry_parameters


def primary_univariate_entries(entries: Sequence[ModelEntry]) -> list[ModelEntry]:
    """Return only models belonging to the primary same-input univariate lane."""

    return [
        entry for entry in entries if lane_for_model(entry.class_name) is RealGameLane.UNIVARIATE
    ]


def build_lane_matrix(
    games: Sequence[str],
    entries: Sequence[ModelEntry],
) -> list[dict[str, Any]]:
    """Materialize all StatsForecast model-game rows before any forecasting runs."""

    rows: list[dict[str, Any]] = []
    for game in games:
        for entry in entries:
            lane = lane_for_model(entry.class_name)
            if lane is RealGameLane.UNIVARIATE:
                planned_status = "EVALUATE_PRIMARY"
            elif lane is RealGameLane.EXOGENOUS:
                planned_status = "DEFER_TO_EXOGENOUS_LANE"
            else:
                planned_status = "EXPECTED_NEGATIVE_CONTROL"
            rows.append(
                {
                    "game": game,
                    "model_id": entry.model_id,
                    "model_name": entry.class_name,
                    "lane": lane.value,
                    "planned_status": planned_status,
                }
            )
    return rows


def _normalized_path(data_root: Path, game: str) -> Path:
    candidates = (
        data_root / game / "normalized" / f"{game}.csv",
        data_root / "normalized" / f"{game}.csv",
        data_root / f"{game}.csv",
    )
    for path in candidates:
        if path.is_file():
            return path
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"missing normalized CSV for {game}; searched: {searched}")


def load_normalized_frames(
    data_root: Path,
    games: Sequence[str],
) -> dict[str, pd.DataFrame]:
    """Load normalized CSVs produced by ``data acquire --games ...``."""

    return {game: pd.read_csv(_normalized_path(data_root, game)) for game in games}


@contextmanager
def resolved_statsforecast_catalog(models_module: Any) -> Iterator[None]:
    """Temporarily project certified StatsForecast parameters into broad-catalog entries.

    ``unified_campaign`` owns the evaluation protocol and selects entries through its
    module-level catalog builder. This scoped adapter preserves that implementation while
    ensuring the selected StatsForecast entries carry the same constructor parameters that
    passed runtime/property certification. The original builder is always restored.
    """

    original_builder = unified_campaign.build_catalog

    def build_resolved_catalog() -> list[ModelEntry]:
        resolved: list[ModelEntry] = []
        for entry in original_builder():
            if entry.library != "statsforecast":
                resolved.append(entry)
                continue
            parameters = resolve_entry_parameters(entry, models_module)
            resolved.append(replace(entry, default_params=parameters))
        return resolved

    unified_campaign.build_catalog = build_resolved_catalog
    try:
        yield
    finally:
        unified_campaign.build_catalog = original_builder


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_statsforecast_development_campaign(
    *,
    data_root: Path,
    output_dir: Path,
    git_commit: str,
    games: tuple[str, ...] = tuple(known_games()),
    seed: int = 1,
    folds: int = 5,
    test_size: int = 20,
    min_train_size: int = 100,
    holdout_size: int = 50,
    gap: int = 0,
    device: str = "cpu",
    precision: str = "32",
    models_module: Any | None = None,
) -> dict[str, Any]:
    """Run the primary StatsForecast development lane on normalized real-game data."""

    entries = statsforecast_entries()
    primary = primary_univariate_entries(entries)
    if len(entries) != 41 or len(primary) != 39:
        raise ValueError(
            "unexpected StatsForecast lane inventory: "
            f"all={len(entries)} primary_univariate={len(primary)}"
        )

    lane_matrix = build_lane_matrix(games, entries)
    if len(lane_matrix) != 41 * len(games):
        raise AssertionError("StatsForecast lane matrix is incomplete")

    frames = load_normalized_frames(data_root, games)
    config = UnifiedCampaignConfig(
        output_dir=output_dir,
        git_commit=git_commit,
        games=games,
        model_ids=tuple(entry.model_id for entry in primary),
        seeds=(seed,),
        folds=folds,
        test_size=test_size,
        min_train_size=min_train_size,
        holdout_size=holdout_size,
        gap=gap,
        device=device,
        precision=precision,
        max_trials=1,
        parallel_trials=1,
    )

    if models_module is None:
        models_module = importlib.import_module("statsforecast.models")

    with resolved_statsforecast_catalog(models_module):
        campaign = unified_campaign.run_unified_campaign(frames, config)

    write_json(output_dir / "STATSFORECAST_LANE_MATRIX.json", lane_matrix)
    summary = {
        "schema_version": 1,
        "library": "statsforecast",
        "phase": "development_rolling",
        "git_commit": git_commit,
        "games": list(games),
        "seed": seed,
        "statsforecast_models": len(entries),
        "primary_univariate_models": len(primary),
        "full_model_game_rows": len(lane_matrix),
        "primary_model_game_rows": len(primary) * len(games),
        "lane_counts_per_game": {
            RealGameLane.UNIVARIATE.value: 39,
            RealGameLane.EXOGENOUS.value: 1,
            RealGameLane.EXPECTED_NEGATIVE_CONTROL.value: 1,
        },
        "primary_matrix_complete": bool(campaign["matrix_complete"]),
        "primary_status": campaign["status"],
        "primary_status_counts": campaign["status_counts"],
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
    }
    write_json(output_dir / "STATSFORECAST_REAL_GAME_SUMMARY.json", summary)
    write_manifest_and_sums(output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run StatsForecast Phase C development evaluation on six-game normalized data."
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", default=",".join(known_games()))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=100)
    parser.add_argument("--holdout-size", type=int, default=50)
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--device", choices=["cpu", "auto"], default="cpu")
    parser.add_argument("--precision", choices=["32"], default="32")
    parser.add_argument("--git-commit", default=None)
    args = parser.parse_args(argv)

    games = tuple(item.strip() for item in args.games.split(",") if item.strip())
    summary = run_statsforecast_development_campaign(
        data_root=args.data_root,
        output_dir=args.output,
        git_commit=args.git_commit or _git_commit(),
        games=games,
        seed=args.seed,
        folds=args.folds,
        test_size=args.test_size,
        min_train_size=args.min_train_size,
        holdout_size=args.holdout_size,
        gap=args.gap,
        device=args.device,
        precision=args.precision,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["primary_matrix_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_lane_matrix",
    "load_normalized_frames",
    "main",
    "primary_univariate_entries",
    "resolved_statsforecast_catalog",
    "run_statsforecast_development_campaign",
]
