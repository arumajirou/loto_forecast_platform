from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from loto.data.lotteries import get_lottery_spec
from loto.data.parser import parse_file
from loto.evaluation.taj21_artifacts import (
    build_verification_report,
    regenerate_sha256sums,
    write_artifact_manifest,
    write_json,
)
from loto.evaluation.taj21_fold_evidence import augment_fold_and_seed_evidence
from loto.evaluation.taj21_paired_comparison import build_paired_comparisons
from loto.evaluation.unified_campaign import UnifiedCampaignConfig, run_unified_campaign
from loto.game.geometry import known_games

APPROVED_SEEDS = (42, 1729, 20260730)
FOLDS = 5
TEST_SIZE = 20
MIN_TRAIN_SIZE = 100
HOLDOUT_SIZE = 50
GAP = 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    root = Path(__file__).resolve().parents[2]
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _load_inputs(
    input_dir: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, str]]:
    root = input_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"TAJ21_DATA_DIR is not a directory: {root}")
    frames: dict[str, pd.DataFrame] = {}
    files: list[dict[str, Any]] = []
    before: dict[str, str] = {}
    for game in known_games():
        path = root / f"{game}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical development CSV: {path}")
        digest = _sha256(path)
        spec = get_lottery_spec(game)
        frame, parser_meta = parse_file(path, spec)
        frames[game] = frame
        before[game] = digest
        files.append(
            {
                "game": game,
                "filename": path.name,
                "sha256": digest,
                "rows": int(len(frame)),
                "parser": "loto.data.parser.parse_file",
                "encoding": parser_meta["encoding"],
                "separator": parser_meta["sep"],
            }
        )
    return (
        frames,
        {
            "schema_version": "taj21-full-input-manifest-v1",
            "games": list(known_games()),
            "files": files,
            "synthetic": False,
            "raw_files_mutated": False,
        },
        before,
    )


def _verify_raw_immutable(input_dir: Path, before: dict[str, str]) -> None:
    for game, expected in before.items():
        path = input_dir.resolve() / f"{game}.csv"
        actual = _sha256(path)
        if actual != expected:
            raise AssertionError(
                f"raw input mutated for {game}: expected={expected} actual={actual}"
            )


def run_full(
    *,
    input_dir: Path,
    output: Path,
    git_commit: str,
    device: str,
    precision: str,
    max_trials: int,
    parallel_trials: int,
    max_steps: int,
    wall_time_seconds: int,
    gpu_count: int,
    gpu_memory_bytes: int,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to reuse full OOF output directory: {output}")
    frames, input_manifest, raw_before = _load_inputs(input_dir)
    config = UnifiedCampaignConfig(
        output_dir=output.resolve(),
        git_commit=git_commit,
        games=tuple(known_games()),
        model_ids=None,
        seeds=APPROVED_SEEDS,
        folds=FOLDS,
        test_size=TEST_SIZE,
        min_train_size=MIN_TRAIN_SIZE,
        holdout_size=HOLDOUT_SIZE,
        gap=GAP,
        device=device,
        precision=precision,
        max_trials=max_trials,
        parallel_trials=parallel_trials,
        max_steps=max_steps,
        wall_time_seconds=wall_time_seconds,
        gpu_count=gpu_count,
        gpu_memory_bytes=gpu_memory_bytes,
    )
    summary = run_unified_campaign(frames, config)
    summary = augment_fold_and_seed_evidence(frames, config, summary)
    comparisons = build_paired_comparisons(summary["results"], config.games)
    summary["scientific_evidence_schema_version"] = "taj21-full-oof-evidence-v1"
    summary["input_manifest"] = "INPUT_MANIFEST.json"
    summary["paired_comparisons"] = "PAIRED_COMPARISONS.json"
    write_json(config.output_dir / "campaign_summary.json", summary)
    write_json(config.output_dir / "INPUT_MANIFEST.json", input_manifest)
    write_json(config.output_dir / "PAIRED_COMPARISONS.json", comparisons)
    report = build_verification_report(
        summary,
        comparisons,
        git_commit=git_commit,
        folds=FOLDS,
    )
    write_json(config.output_dir / "VERIFICATION_REPORT.json", report)
    write_artifact_manifest(config.output_dir, git_commit=git_commit)
    sums_sha = regenerate_sha256sums(config.output_dir)
    _verify_raw_immutable(input_dir, raw_before)
    return {
        "summary": summary,
        "verification_report": report,
        "sha256sums_sha256": sums_sha,
        "output": str(config.output_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--precision", choices=["32", "16-mixed", "bf16-mixed"], default="32")
    parser.add_argument("--max-trials", type=int, default=10)
    parser.add_argument("--parallel-trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--wall-time-seconds", type=int, default=1800)
    parser.add_argument("--gpu-count", type=int, default=0)
    parser.add_argument("--gpu-memory-bytes", type=int, default=0)
    args = parser.parse_args()
    try:
        result = run_full(
            input_dir=args.input_dir,
            output=args.output,
            git_commit=args.git_commit or _git_commit(),
            device=args.device,
            precision=args.precision,
            max_trials=args.max_trials,
            parallel_trials=args.parallel_trials,
            max_steps=args.max_steps,
            wall_time_seconds=args.wall_time_seconds,
            gpu_count=args.gpu_count,
            gpu_memory_bytes=args.gpu_memory_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - formal runner must fail visibly
        print("TAJ21_FULL_OOF=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2
    summary = result["summary"]
    report = result["verification_report"]
    print("TAJ21_FULL_OOF=EXECUTED")
    print(f"GIT_COMMIT={summary['git_commit']}")
    print(f"CATALOG_MODELS={summary['catalog_models']}")
    print(f"MODEL_GAME_PAIRS={summary['observed_model_game_pairs']}/{summary['expected_model_game_pairs']}")
    print(f"CANDIDATE_SUCCEEDED={report['candidate_succeeded']}")
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"OUTPUT={result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
