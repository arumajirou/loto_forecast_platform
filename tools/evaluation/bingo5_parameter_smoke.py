"""Run a one-config real-execution smoke over the canonical 250 Bingo5 identities."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from loto.data.lotteries import get_lottery_spec
from loto.data.parser import parse_file
from loto.evaluation.parameter_sweep.artifacts import regenerate_sha256sums
from loto.evaluation.parameter_sweep.smoke import run_bingo5_smoke
from loto.evaluation.taj21_snapshot import validate_snapshot_item

TARGET_GAME = "bingo5"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_bingo5(input_dir: Path):
    path = input_dir.resolve() / "bingo5.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing canonical Bingo5 CSV: {path}")
    digest = _sha256(path)
    spec = get_lottery_spec(TARGET_GAME)
    frame, parser_meta = parse_file(path, spec)
    validate_snapshot_item(
        TARGET_GAME,
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
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--wall-time-seconds", type=int, default=300)
    parser.add_argument("--gpu-count", type=int, default=0)
    parser.add_argument("--gpu-memory-bytes", type=int, default=0)
    args = parser.parse_args()

    if not args.run_root.is_dir():
        print("BINGO5_PARAMETER_SMOKE=BLOCKED")
        print(f"REASON=run root does not exist; run prepare first: {args.run_root}")
        return 2

    try:
        frame, digest = _load_bingo5(args.input_dir)
        result = run_bingo5_smoke(
            frame,
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
    except Exception as exc:  # noqa: BLE001 - smoke must fail visibly
        print("BINGO5_PARAMETER_SMOKE=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("TARGET_GAME=bingo5")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    counts = result["normalized_status_counts"]
    passed = int(counts.get("SUCCEEDED", 0))
    failed = result["candidate_total"] - passed
    print("BINGO5_PARAMETER_SMOKE=EXECUTED")
    print("TARGET_GAME=bingo5")
    print(f"SMOKE_TOTAL={result['candidate_total']}")
    print(f"SMOKE_PASS={passed}")
    print(f"SMOKE_FAIL={failed}")
    print(f"NOT_ROUTABLE={counts.get('NOT_ROUTABLE', 0)}")
    print(f"UNAVAILABLE={counts.get('UNAVAILABLE', 0)}")
    print(f"EXPECTED_NEGATIVE_CONTROL={counts.get('EXPECTED_NEGATIVE_CONTROL', 0)}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"SHA256SUMS_SHA256={sums_sha}")
    print(f"OUTPUT={result['output']}")
    print(f"CHECKPOINT={result['checkpoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
