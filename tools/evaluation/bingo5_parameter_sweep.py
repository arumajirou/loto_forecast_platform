"""Prepare the isolated Bingo5 parameter-sweep discovery artifacts.

This command is preparation-only. It inventories the canonical 250-model universe,
binds the immutable Bingo5 raw input, extracts installed constructor signatures, and
writes bounded search-space declarations. It never evaluates Holdout/Prospective targets
and never touches the paused TAJ-21 formal checkpoint tree.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.data.lotteries import get_lottery_spec
from loto.data.parser import parse_file
from loto.evaluation.parameter_sweep import (
    PilotRunConfig,
    build_bingo5_inventory,
    build_search_spaces,
)
from loto.evaluation.parameter_sweep.artifacts import atomic_write_json, regenerate_sha256sums
from loto.evaluation.parameter_sweep.contracts import SearchSpaceStatus
from loto.evaluation.taj21_snapshot import validate_snapshot_item

TARGET_GAME = "bingo5"
EXPECTED_IDENTITIES = 250
HOLDOUT_SIZE = 50
COARSE_VALIDATION_SIZE = 20


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=_repo_root(), text=True).strip()


def _git_commit() -> str:
    return _git("rev-parse", "HEAD")


def _code_identity() -> dict[str, Any]:
    paths = [
        _repo_root() / "src" / "loto" / "evaluation" / "parameter_sweep",
        _repo_root() / "tools" / "evaluation" / "bingo5_parameter_sweep.py",
        _repo_root() / "tools" / "evaluation" / "bingo5_parameter_smoke.py",
        _repo_root() / "tools" / "evaluation" / "bingo5_parameter_coarse.py",
    ]
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(item for item in path.rglob("*.py") if item.is_file()))
        elif path.is_file():
            files.append(path)
    file_hashes = {
        path.relative_to(_repo_root()).as_posix(): _sha256(path)
        for path in sorted(set(files))
    }
    aggregate = hashlib.sha256()
    for path, digest in sorted(file_hashes.items()):
        aggregate.update(path.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    status = _git("status", "--porcelain")
    return {
        "git_commit": _git_commit(),
        "git_tree": _git("rev-parse", "HEAD^{tree}"),
        "git_status_clean": not bool(status),
        "tracked_source_sha256": aggregate.hexdigest(),
        "files": file_hashes,
    }


def _nvidia_smi() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,uuid,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"available": True, "rows": rows}


def _load_bingo5(input_dir: Path) -> tuple[Any, dict[str, Any]]:
    path = input_dir.resolve() / f"{TARGET_GAME}.csv"
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
    date_columns = [column for column in frame.columns if "date" in column.lower()]
    date_range: dict[str, Any] = {}
    for column in date_columns:
        series = frame[column].dropna()
        if not series.empty:
            date_range[column] = {"first": str(series.iloc[0]), "last": str(series.iloc[-1])}
    return frame, {
        "game": TARGET_GAME,
        "path": str(path),
        "rows": int(len(frame)),
        "sha256": digest,
        "columns": [str(column) for column in frame.columns],
        "date_range": date_range,
        "parser": {
            "encoding": parser_meta["encoding"],
            "separator": parser_meta["sep"],
        },
        "raw_mutated": False,
    }


def prepare(
    *,
    input_dir: Path,
    run_root: Path,
    run_id: str,
    base_commit: str,
) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"refusing to reuse run root: {run_root}")
    run_root.mkdir(parents=True)

    config = PilotRunConfig(
        base_commit=base_commit,
        run_id=run_id,
        run_root=str(run_root.resolve()),
    )
    frame, data_manifest = _load_bingo5(input_dir)
    development_rows = int(len(frame)) - HOLDOUT_SIZE
    train_rows = development_rows - COARSE_VALIDATION_SIZE
    if train_rows < 2:
        raise ValueError("insufficient Bingo5 Train rows after sealing Holdout and Validation")

    inventory = build_bingo5_inventory()
    if len(inventory) != EXPECTED_IDENTITIES:
        atomic_write_json(
            run_root / "MODEL_INVENTORY_GAP.json",
            {
                "expected": EXPECTED_IDENTITIES,
                "observed": len(inventory),
                "model_ids": [row.model_id for row in inventory],
            },
        )
        raise RuntimeError(
            f"model inventory mismatch: expected={EXPECTED_IDENTITIES} observed={len(inventory)}"
        )

    spaces = build_search_spaces(inventory, train_rows=train_rows)
    parameter_rows = [
        {
            "model_id": row.model_id,
            "library": row.library,
            "constructor_signature": row.constructor_signature,
            "required_args": list(row.required_args),
            "optional_args": list(row.optional_args),
            "parameters": [item.model_dump(mode="json") for item in row.parameter_inventory],
        }
        for row in inventory
    ]
    status_counts: dict[str, int] = {}
    for space in spaces:
        status_counts[space.status.value] = status_counts.get(space.status.value, 0) + 1

    runtime = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": max(int(os.cpu_count() or 1), 1),
        "gpu": _nvidia_smi(),
    }
    split_contract = {
        "raw_rows": int(len(frame)),
        "holdout_size": HOLDOUT_SIZE,
        "development_rows": development_rows,
        "coarse_validation_size": COARSE_VALIDATION_SIZE,
        "coarse_train_rows": train_rows,
        "holdout": "CLOSED",
        "prospective": "CLOSED",
        "promotion": "CLOSED",
    }
    atomic_write_json(run_root / "RUN_CONFIG.json", config)
    atomic_write_json(run_root / "DATA_HASHES.json", data_manifest)
    atomic_write_json(run_root / "SPLIT_CONTRACT.json", split_contract)
    atomic_write_json(run_root / "MODEL_INVENTORY.json", inventory)
    atomic_write_json(run_root / "PARAMETER_INVENTORY.json", parameter_rows)
    atomic_write_json(run_root / "SEARCH_SPACES.json", spaces)
    atomic_write_json(run_root / "CODE_HASH.json", _code_identity())
    atomic_write_json(run_root / "GPU_INFO.json", runtime["gpu"])
    atomic_write_json(run_root / "RUNTIME_SUMMARY.json", runtime)
    atomic_write_json(
        run_root / "PREPARE_SUMMARY.json",
        {
            "target_game": TARGET_GAME,
            "base_commit": base_commit,
            "git_commit": _git_commit(),
            "run_id": run_id,
            "run_root": str(run_root.resolve()),
            "data_rows": data_manifest["rows"],
            "data_sha256": data_manifest["sha256"],
            "model_inventory_count": len(inventory),
            "libraries": sorted({row.library for row in inventory}),
            "search_space_count": len(spaces),
            "search_space_status_counts": status_counts,
            "smoke_total": 0,
            "smoke_pass": 0,
            "smoke_fail": 0,
            "split_contract": split_contract,
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "primary_metric": "hit_at_1",
            "ready_model_count": sum(
                1 for item in spaces if item.status is SearchSpaceStatus.READY
            ),
        },
    )
    sums_sha = regenerate_sha256sums(run_root)
    return {
        "config": config,
        "data_manifest": data_manifest,
        "inventory": inventory,
        "spaces": spaces,
        "status_counts": status_counts,
        "split_contract": split_contract,
        "sha256sums_sha256": sums_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-commit", default=None)
    args = parser.parse_args()
    try:
        result = prepare(
            input_dir=args.input_dir,
            run_root=args.run_root,
            run_id=args.run_id,
            base_commit=args.base_commit or _git_commit(),
        )
    except Exception as exc:  # noqa: BLE001 - preparation must fail visibly
        print("BINGO5_PARAMETER_SWEEP_PREPARE=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("TARGET_GAME=bingo5")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    summary = result["data_manifest"]
    inventory = result["inventory"]
    print("BINGO5_PARAMETER_SWEEP_PREPARE=PASS")
    print("TARGET_GAME=bingo5")
    print(f"BASE_COMMIT={result['config'].base_commit}")
    print(f"GIT_COMMIT={_git_commit()}")
    print(f"RUN_ID={result['config'].run_id}")
    print(f"RUN_ROOT={result['config'].run_root}")
    print(f"DATA_ROWS={summary['rows']}")
    print(f"DATA_SHA256={summary['sha256']}")
    print(f"MODEL_INVENTORY_COUNT={len(inventory)}")
    print("LIBRARIES=" + ",".join(sorted({row.library for row in inventory})))
    print(f"SEARCH_SPACE_COUNT={len(result['spaces'])}")
    for status, count in sorted(result["status_counts"].items()):
        print(f"SEARCH_SPACE_{status}={count}")
    print("SMOKE_TOTAL=0")
    print("SMOKE_PASS=0")
    print("SMOKE_FAIL=0")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
