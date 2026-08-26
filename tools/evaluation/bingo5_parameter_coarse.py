"""Execute the bounded OFAT coarse-search phase for the isolated Bingo5 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from loto.data.lotteries import get_lottery_spec
from loto.data.parser import parse_file
from loto.evaluation.parameter_sweep.artifacts import regenerate_sha256sums
from loto.evaluation.parameter_sweep.contracts import ModelInventoryRow, ModelSearchSpace
from loto.evaluation.parameter_sweep.trials import run_coarse_ofat
from loto.evaluation.taj21_snapshot import validate_snapshot_item


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_frame(input_dir: Path):
    path = input_dir.resolve() / "bingo5.csv"
    digest = _sha256(path)
    frame, parser_meta = parse_file(path, get_lottery_spec("bingo5"))
    validate_snapshot_item(
        "bingo5",
        rows=int(len(frame)),
        sha256=digest,
        encoding=str(parser_meta["encoding"]),
        separator=str(parser_meta["sep"]),
    )
    return frame, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--precision", choices=["32", "16-mixed", "bf16-mixed"], default="32")
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--wall-time-seconds", type=int, default=600)
    parser.add_argument("--gpu-count", type=int, default=0)
    parser.add_argument("--gpu-memory-bytes", type=int, default=0)
    args = parser.parse_args()

    try:
        inventory_payload = json.loads((args.run_root / "MODEL_INVENTORY.json").read_text())
        spaces_payload = json.loads((args.run_root / "SEARCH_SPACES.json").read_text())
        inventory = [ModelInventoryRow.model_validate(item) for item in inventory_payload]
        spaces = [ModelSearchSpace.model_validate(item) for item in spaces_payload]
        frame, digest = _load_frame(args.input_dir)
        result = run_coarse_ofat(
            frame,
            inventory,
            spaces,
            run_root=args.run_root,
            input_sha256=digest,
            git_commit=args.git_commit,
            device=args.device,
            precision=args.precision,
            max_steps=args.max_steps,
            wall_time_seconds=args.wall_time_seconds,
            gpu_count=args.gpu_count,
            gpu_memory_bytes=args.gpu_memory_bytes,
        )
        sums_sha = regenerate_sha256sums(args.run_root)
    except Exception as exc:  # noqa: BLE001 - coarse phase must fail visibly
        print("BINGO5_PARAMETER_COARSE=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    print("BINGO5_PARAMETER_COARSE=EXECUTED")
    print("TARGET_GAME=bingo5")
    print(f"READY_MODELS={result['ready_models']}")
    print(f"TRIALS={result['trials']}")
    print(f"TRIALS_SUCCEEDED={result['succeeded']}")
    print(f"TRIALS_FAILED={result['failed']}")
    print(f"CONTRACT_SHA256={result['contract_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"SHA256SUMS_SHA256={sums_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
