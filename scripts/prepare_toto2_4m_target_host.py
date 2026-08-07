from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.toto2_campaign.certification_bundle import sha256_file  # noqa: E402
from loto.toto2_campaign.model_manifest import (  # noqa: E402
    ARTIFACT_SHA256,
    ARTIFACT_SIZE_BYTES,
    MODEL_REVISION,
)
from loto.toto2_campaign.request_factory import (  # noqa: E402
    FORMAL_GAMES,
    load_history_export,
    write_request_set,
)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _run(command: list[str], *, timeout: int = 30) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {command!r} returncode={completed.returncode} "
            f"stderr={completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _verify_git(expected_head: str) -> dict[str, Any]:
    actual_head = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if actual_head != expected_head:
        raise ValueError(f"Git HEAD mismatch: expected={expected_head} actual={actual_head}")
    tracked_status = _run(
        [
            "git",
            "-C",
            str(ROOT),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ]
    )
    if tracked_status:
        raise ValueError("tracked working tree changes must be resolved before certification")
    branch = _run(["git", "-C", str(ROOT), "branch", "--show-current"])
    return {"head_sha": actual_head, "branch": branch, "tracked_clean": True}


def _verify_snapshot(snapshot: Path) -> dict[str, Any]:
    if snapshot.name != MODEL_REVISION:
        raise ValueError(
            f"snapshot directory must equal pinned revision: {MODEL_REVISION}"
        )
    files: dict[str, Any] = {}
    for name, expected_hash in ARTIFACT_SHA256.items():
        path = snapshot / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"snapshot artifact is missing or unsafe: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"snapshot artifact hash mismatch: {name} "
                f"expected={expected_hash} actual={actual_hash}"
            )
        expected_size = ARTIFACT_SIZE_BYTES.get(name)
        if expected_size is not None and path.stat().st_size != expected_size:
            raise ValueError(f"snapshot artifact size mismatch: {name}")
        files[name] = {
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": actual_hash,
        }
    return {"revision": MODEL_REVISION, "files": files}


def _verify_isolated_runtime(python_path: Path) -> dict[str, Any]:
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise ValueError(f"isolated Python is missing or not executable: {python_path}")
    code = """
import importlib.metadata
import json
import platform
import torch
print(json.dumps({
    'python': platform.python_version(),
    'torch': torch.__version__,
    'torch_cuda': torch.version.cuda,
    'toto_2': importlib.metadata.version('toto-2'),
    'toto_models': importlib.metadata.version('toto-models'),
}, sort_keys=True))
"""
    payload = json.loads(_run([str(python_path), "-c", code]))
    if not str(payload.get("python", "")).startswith("3.12."):
        raise ValueError(f"isolated Python must be 3.12.x: {payload}")
    if payload.get("toto_2") != "2.0.0":
        raise ValueError(f"toto-2 version mismatch: {payload}")
    if payload.get("toto_models") != "1.0.0":
        raise ValueError(f"toto-models version mismatch: {payload}")
    if not str(payload.get("torch", "")).startswith("2.13.0"):
        raise ValueError(f"Torch version mismatch: {payload}")
    return payload


def _query_gpu_inventory() -> list[dict[str, str]]:
    if shutil.which("nvidia-smi") is None:
        raise ValueError("nvidia-smi is required for the CUDA half of the formal matrix")
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            raise ValueError(f"unexpected nvidia-smi inventory row: {line!r}")
        rows.append(
            {
                "name": parts[0],
                "uuid": parts[1],
                "memory_total_mib": parts[2],
                "driver_version": parts[3],
            }
        )
    if not rows:
        raise ValueError("no NVIDIA GPU was reported")
    return rows


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    if shutil.which("uv") is None:
        raise ValueError("uv is required")
    git = _verify_git(args.expected_head)
    snapshot = _verify_snapshot(args.snapshot)
    lock_path = ROOT / "environments" / "toto2-4m-py312" / "uv.lock"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise ValueError(f"isolated uv.lock is missing or unsafe: {lock_path}")
    lock_sha256 = sha256_file(lock_path)
    runtime = _verify_isolated_runtime(args.isolated_python)
    gpu_inventory = _query_gpu_inventory()

    histories = {
        game: load_history_export(args.history_root / f"{game}.json")
        for game in FORMAL_GAMES
    }
    requests_root = args.output_root / "requests"
    request_manifest = write_request_set(
        histories,
        output_root=requests_root,
        snapshot_path=args.snapshot,
    )
    lock_review_path = args.output_root / "lock_review.pending.json"
    _atomic_write_json(
        lock_review_path,
        {
            "schema_version": 1,
            "status": "PENDING",
            "reviewer": "",
            "reviewed_at": "",
            "lock_sha256": lock_sha256,
            "dependency_sources_reviewed": False,
            "package_hashes_reviewed": False,
            "licenses_reviewed": False,
        },
    )
    result = {
        "schema_version": 1,
        "status": "PREPARED_REVIEW_REQUIRED",
        "prepared_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git": git,
        "snapshot": snapshot,
        "isolated_runtime": runtime,
        "gpu_inventory": gpu_inventory,
        "lock_path": str(lock_path.resolve()),
        "lock_sha256": lock_sha256,
        "request_manifest_path": str(
            (requests_root / "REQUEST_MANIFEST.json").resolve()
        ),
        "request_count": request_manifest["request_count"],
        "lock_review_path": str(lock_review_path.resolve()),
        "matrix_execution_started": False,
    }
    _atomic_write_json(args.output_root / "PREPARATION_RESULT.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare Toto 2.0 4M target-host certification inputs"
    )
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--isolated-python", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"TARGET_HOST_PREPARATION=FAILED\nERROR={type(exc).__name__}: {exc}")
        return 2
    print("TARGET_HOST_PREPARATION=PASS")
    print(f"REQUEST_COUNT={result['request_count']}")
    print(f"LOCK_REVIEW={result['lock_review_path']}")
    print("MATRIX_EXECUTION_STARTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
