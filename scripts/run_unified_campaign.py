#!/usr/bin/env python3
"""Run the unified all-model x all-game development evaluation campaign."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from loto.evaluation.unified_campaign import (
    UnifiedCampaignConfig,
    build_campaign_plan,
    run_unified_campaign,
)
from loto.game.geometry import geometry_for, known_games


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _synthetic(game: str, rows: int, seed: int) -> pd.DataFrame:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    payload = []
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    for draw in range(rows):
        if geometry.family == "select":
            values = np.sort(rng.choice(universe, size=geometry.positions, replace=False))
        else:
            values = rng.choice(universe, size=geometry.positions, replace=True)
        payload.append(
            {
                "draw_no": draw + 1,
                **dict(zip(geometry.column_names(), values.tolist(), strict=True)),
            }
        )
    return pd.DataFrame(payload)


def _load_frames(args: argparse.Namespace, games: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    if args.synthetic:
        return {game: _synthetic(game, args.synthetic_rows, args.synthetic_seed) for game in games}
    if not args.input_dir:
        raise SystemExit("either --input-dir or --synthetic is required")
    root = Path(args.input_dir)
    frames: dict[str, pd.DataFrame] = {}
    for game in games:
        path = root / f"{game}.csv"
        if not path.is_file():
            raise SystemExit(f"missing input CSV for {game}: {path}")
        frames[game] = pd.read_csv(path)
    return frames


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute every requested broad-catalog model/game combination under one "
            "development-only protocol. Non-routable combinations remain in the result matrix."
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--input-dir", default=None, help="directory containing <game>.csv files")
    parser.add_argument("--synthetic", action="store_true", help="use deterministic synthetic data")
    parser.add_argument("--synthetic-rows", type=int, default=220)
    parser.add_argument("--synthetic-seed", type=int, default=7)
    parser.add_argument("--games", default=",".join(known_games()))
    parser.add_argument(
        "--models", default=None, help="comma-separated broad catalog IDs; default=all"
    )
    parser.add_argument("--seeds", default="42,1729,20260730")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=100)
    parser.add_argument("--holdout-size", type=int, default=50)
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--precision", choices=["32", "16-mixed", "bf16-mixed"], default="32")
    parser.add_argument("--max-trials", type=int, default=10)
    parser.add_argument("--parallel-trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--wall-time-seconds", type=int, default=1800)
    parser.add_argument("--gpu-count", type=int, default=0)
    parser.add_argument("--gpu-memory-bytes", type=int, default=0)
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--plan-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    games = tuple(item.strip() for item in args.games.split(",") if item.strip())
    models = (
        tuple(item.strip() for item in args.models.split(",") if item.strip())
        if args.models is not None
        else None
    )
    seeds = tuple(sorted(int(item.strip()) for item in args.seeds.split(",") if item.strip()))
    config = UnifiedCampaignConfig(
        output_dir=Path(args.output),
        git_commit=args.git_commit or _git_commit(),
        games=games,
        model_ids=models,
        seeds=seeds,
        folds=args.folds,
        test_size=args.test_size,
        min_train_size=args.min_train_size,
        holdout_size=args.holdout_size,
        gap=args.gap,
        device=args.device,
        precision=args.precision,
        max_trials=args.max_trials,
        parallel_trials=args.parallel_trials,
        max_steps=args.max_steps,
        wall_time_seconds=args.wall_time_seconds,
        gpu_count=args.gpu_count,
        gpu_memory_bytes=args.gpu_memory_bytes,
    )
    if args.plan_only:
        plan = build_campaign_plan(config)
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "games": list(config.games),
                    "model_game_pairs": len(plan),
                    "plan": plan,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    frames = _load_frames(args, games)
    result = run_unified_campaign(frames, config)
    print(
        json.dumps(
            {
                "status": result["status"],
                "matrix_complete": result["matrix_complete"],
                "catalog_models": result["catalog_models"],
                "expected_model_game_pairs": result["expected_model_game_pairs"],
                "observed_model_game_pairs": result["observed_model_game_pairs"],
                "status_counts": result["status_counts"],
                "primary_metric": result["primary_metric"],
                "holdout_evaluated": result["holdout_evaluated"],
                "prospective_evaluated": result["prospective_evaluated"],
                "output": str(config.output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["matrix_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
