from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from loto.data.lotteries import get_lottery_spec
from loto.data.parser import parse_file
from loto.evaluation.unified_campaign import UnifiedCampaignConfig, run_unified_campaign
from loto.game.geometry import geometry_for, known_games

BASELINE_SEEDS = (42, 1729, 20260730)
BASELINE_FOLDS = 5
BASELINE_TEST_SIZE = 20
BASELINE_MIN_TRAIN_SIZE = 100
BASELINE_HOLDOUT_SIZE = 50
BASELINE_GAP = 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _input_manifest(input_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"TAJ21_DATA_DIR is not a directory: {input_dir}")

    frames: dict[str, pd.DataFrame] = {}
    files: list[dict[str, Any]] = []
    for game in known_games():
        path = input_dir / f"{game}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical development CSV: {path}")
        spec = get_lottery_spec(game)
        frame, parser_meta = parse_file(path, spec)
        geometry = geometry_for(game)
        required_columns = geometry.column_names()
        missing = [column for column in required_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"{game}: missing canonical target columns: {missing}")
        if len(frame) <= BASELINE_HOLDOUT_SIZE:
            raise ValueError(f"{game}: not enough rows to reserve closed Holdout")
        frames[game] = frame
        files.append(
            {
                "game": game,
                "filename": path.name,
                "sha256": _sha256(path),
                "rows": int(len(frame)),
                "parser": "loto.data.parser.parse_file",
                "encoding": parser_meta["encoding"],
                "separator": parser_meta["sep"],
                "target_columns": required_columns,
            }
        )

    manifest = {
        "schema_version": "taj21-baseline-input-manifest-v1",
        "games": list(known_games()),
        "files": files,
        "synthetic": False,
        "raw_files_mutated": False,
    }
    return frames, manifest


def _regenerate_checksums(root: Path) -> str:
    artifacts = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in artifacts]
    sums_path = root / "SHA256SUMS"
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _sha256(sums_path)


def run_baselines(*, input_dir: Path, output: Path, git_commit: str) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse baseline output directory: {output}")

    frames, input_manifest = _input_manifest(input_dir)
    output.mkdir(parents=True)
    (output / "INPUT_MANIFEST.json").write_bytes(_canonical_json(input_manifest) + b"\n")

    campaign_root = output / "campaign"
    config = UnifiedCampaignConfig(
        output_dir=campaign_root,
        git_commit=git_commit,
        games=tuple(known_games()),
        model_ids=(),
        seeds=BASELINE_SEEDS,
        folds=BASELINE_FOLDS,
        test_size=BASELINE_TEST_SIZE,
        min_train_size=BASELINE_MIN_TRAIN_SIZE,
        holdout_size=BASELINE_HOLDOUT_SIZE,
        gap=BASELINE_GAP,
        device="cpu",
        precision="32",
        max_trials=1,
        parallel_trials=1,
        max_steps=1,
        gpu_count=0,
        gpu_memory_bytes=0,
    )
    summary = run_unified_campaign(frames, config)
    if summary.get("holdout_evaluated") is not False:
        raise AssertionError("baseline campaign evaluated Holdout")
    if summary.get("prospective_evaluated") is not False:
        raise AssertionError("baseline campaign evaluated Prospective")
    if summary.get("promotion") is not False:
        raise AssertionError("baseline campaign opened Promotion")

    reference = {
        "schema_version": "taj21-baseline-reference-v1",
        "status": "EXECUTED",
        "git_commit": git_commit,
        "games": list(known_games()),
        "baselines": 7,
        "seeds": list(BASELINE_SEEDS),
        "folds": BASELINE_FOLDS,
        "test_size": BASELINE_TEST_SIZE,
        "min_train_size": BASELINE_MIN_TRAIN_SIZE,
        "holdout_rows_reserved_per_game": BASELINE_HOLDOUT_SIZE,
        "gap": BASELINE_GAP,
        "primary_metric": "hit_at_1",
        "synthetic": False,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "accuracy_claim": False,
        "campaign_summary": "campaign/campaign_summary.json",
    }
    (output / "BASELINE_REFERENCE.json").write_bytes(_canonical_json(reference) + b"\n")
    sums_sha = _regenerate_checksums(output)
    return {
        "output": str(output),
        "sha256sums_sha256": sums_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()

    try:
        result = run_baselines(
            input_dir=args.input_dir,
            output=args.output,
            git_commit=args.git_commit,
        )
    except Exception as exc:  # noqa: BLE001 - formal launcher must fail visibly
        print("TAJ21_BASELINE_EXECUTION=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("SYNTHETIC_FALLBACK=FORBIDDEN")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    print("TAJ21_BASELINE_EXECUTION=EXECUTED")
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    print("SYNTHETIC=FALSE")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
