from __future__ import annotations

import argparse
import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuRow:
    index: int
    name: str
    total_mib: int
    used_mib: int
    free_mib: int


def _run_nvidia_smi(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["nvidia-smi", *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def read_gpus() -> list[GpuRow]:
    proc = _run_nvidia_smi(
        [
            "--query-gpu=index,name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"nvidia-smi GPU query failed rc={proc.returncode}: {proc.stderr.strip()}")
    rows: list[GpuRow] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        parts = [part.strip() for part in raw.split(",", maxsplit=4)]
        if len(parts) != 5:
            raise RuntimeError(f"unexpected nvidia-smi GPU row: {raw!r}")
        rows.append(
            GpuRow(
                index=int(parts[0]),
                name=parts[1],
                total_mib=int(parts[2]),
                used_mib=int(parts[3]),
                free_mib=int(parts[4]),
            )
        )
    if not rows:
        raise RuntimeError("no NVIDIA GPU detected")
    return rows


def read_compute_apps() -> list[str]:
    proc = _run_nvidia_smi(
        [
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def show_status(required_free_mib: int) -> bool:
    rows = read_gpus()
    max_free = max(row.free_mib for row in rows)
    print(f"GPU_COUNT={len(rows)}")
    print(f"GPU_REQUIRED_FREE_MIB={required_free_mib}")
    for row in rows:
        print(
            "GPU="
            f"{row.index} name={row.name} total_mib={row.total_mib} "
            f"used_mib={row.used_mib} free_mib={row.free_mib}"
        )
    apps = read_compute_apps()
    print(f"GPU_COMPUTE_PROCESS_COUNT={len(apps)}")
    for app in apps:
        print(f"GPU_PROCESS={app}")
    ready = max_free >= required_free_mib
    print(f"GPU_READY={'YES' if ready else 'NO'}")
    print(f"GPU_MAX_FREE_MIB={max_free}")
    return ready


def wait_for_gpu(required_free_mib: int, interval_seconds: float, timeout_seconds: float) -> int:
    started = time.monotonic()
    last_process_dump = -30.0
    while True:
        rows = read_gpus()
        max_free = max(row.free_mib for row in rows)
        elapsed = time.monotonic() - started
        pct = min(100.0, 100.0 * max_free / required_free_mib)
        width = 40
        filled = min(width, int(width * pct / 100.0))
        bar = "#" * filled + "-" * (width - filled)
        print(
            f"\r[{bar}] {pct:6.2f}% free={max_free}/{required_free_mib} MiB "
            f"elapsed={int(elapsed)}s",
            end="",
            flush=True,
        )
        if max_free >= required_free_mib:
            print()
            print("TAJ19_GPU_WAIT=PASS")
            print(f"GPU_MAX_FREE_MIB={max_free}")
            return 0
        if timeout_seconds > 0 and elapsed >= timeout_seconds:
            print()
            print("TAJ19_GPU_WAIT=BLOCKED")
            print("REASON=GPU_WAIT_TIMEOUT")
            print(f"GPU_MAX_FREE_MIB={max_free}")
            return 20
        if elapsed - last_process_dump >= 30.0:
            print()
            apps = read_compute_apps()
            print(f"GPU_COMPUTE_PROCESS_COUNT={len(apps)}")
            for app in apps:
                print(f"GPU_PROCESS={app}")
            last_process_dump = elapsed
        time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-19 live GPU readiness helper")
    parser.add_argument("mode", choices=("status", "wait"))
    parser.add_argument(
        "--required-free-mib",
        type=int,
        default=int(os.environ.get("TAJ19_GPU_REQUIRED_FREE_MIB", "7168")),
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(os.environ.get("TAJ19_GPU_WAIT_INTERVAL", "5")),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("TAJ19_GPU_WAIT_TIMEOUT", "0")),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.required_free_mib < 1:
        raise SystemExit("--required-free-mib must be >= 1")
    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be > 0")
    if args.timeout_seconds < 0:
        raise SystemExit("--timeout-seconds must be >= 0")
    if args.mode == "status":
        return 0 if show_status(args.required_free_mib) else 20
    return wait_for_gpu(args.required_free_mib, args.interval_seconds, args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
