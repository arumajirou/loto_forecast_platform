from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORKER = ROOT / "scripts" / "experiments" / "run_numbers3_n1_rolling_worker.py"

OUTPUT_ROOT = ROOT / "artifacts" / "numbers3" / "n1_rolling_parallel"

MONITOR_CSV = OUTPUT_ROOT / "gpu_monitor.csv"
STATUS_CSV = OUTPUT_ROOT / "scheduler_status.csv"


@dataclass(frozen=True)
class JobSpec:
    model: str
    shard_index: int
    shard_count: int
    budget_mib: int

    @property
    def job_id(self) -> str:
        return f"{self.model}_s{self.shard_index + 1}of{self.shard_count}"


@dataclass
class RunningJob:
    spec: JobSpec
    process: subprocess.Popen[str]
    log_handle: object
    started_at: float
    log_path: Path


# 実測値より十分大きな予約値を設定。
# CUDA context、データローダー、一時テンソルを含む安全予算。
JOB_SPECS = [
    JobSpec("Informer", 0, 3, 1800),
    JobSpec("Informer", 1, 3, 1800),
    JobSpec("Informer", 2, 3, 1800),
    JobSpec("TimesNet", 0, 2, 600),
    JobSpec("TimesNet", 1, 2, 600),
    JobSpec("KAN", 0, 2, 600),
    JobSpec("KAN", 1, 2, 600),
    JobSpec("TCN", 0, 2, 500),
    JobSpec("TCN", 1, 2, 500),
    JobSpec("NLinear", 0, 1, 500),
    JobSpec("MLP", 0, 1, 500),
]


def query_gpu() -> dict[str, float]:
    command = [
        "nvidia-smi",
        "--query-gpu="
        "memory.total,"
        "memory.used,"
        "memory.free,"
        "utilization.gpu,"
        "temperature.gpu,"
        "power.draw",
        "--format=csv,noheader,nounits",
        "--id=0",
    ]

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    values = [value.strip() for value in result.stdout.strip().split(",")]

    if len(values) != 6:
        raise RuntimeError(f"Unexpected nvidia-smi output: {result.stdout!r}")

    return {
        "total_mib": float(values[0]),
        "used_mib": float(values[1]),
        "free_mib": float(values[2]),
        "gpu_util_percent": float(values[3]),
        "temperature_c": float(values[4]),
        "power_w": float(values[5]),
    }


def append_csv(
    path: Path,
    fieldnames: list[str],
    row: dict[str, object],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    exists = path.exists()

    with path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        if not exists:
            writer.writeheader()

        writer.writerow(row)


def start_job(
    spec: JobSpec,
    rolling_points: int,
) -> RunningJob:
    model_dir = (
        OUTPUT_ROOT
        / spec.model.lower()
        / (f"shard_{spec.shard_index:02d}_of_{spec.shard_count:02d}")
    )

    model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = model_dir / "run.log"

    log_handle = log_path.open(
        "w",
        encoding="utf-8",
    )

    env = os.environ.copy()

    env.update(
        {
            "NUMBERS3_MODEL_NAME": spec.model,
            "NUMBERS3_ROLLING_POINTS": str(rolling_points),
            "NUMBERS3_SHARD_INDEX": str(spec.shard_index),
            "NUMBERS3_SHARD_COUNT": str(spec.shard_count),
            "PYTORCH_ALLOC_CONF": ("expandable_segments:True"),
            "PYTHONUNBUFFERED": "1",
            "OMP_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "NUMEXPR_NUM_THREADS": "2",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }
    )

    command = [
        "uv",
        "run",
        "--frozen",
        "python",
        str(WORKER),
    ]

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    return RunningJob(
        spec=spec,
        process=process,
        log_handle=log_handle,
        started_at=time.monotonic(),
        log_path=log_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--rolling-points",
        type=int,
        default=50,
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--reserve-mib",
        type=int,
        default=2500,
    )

    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
    )

    args = parser.parse_args()

    if not WORKER.exists():
        raise FileNotFoundError(WORKER)

    if shutil.which("nvidia-smi") is None:
        raise RuntimeError("nvidia-smi was not found")

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 古い監視情報だけ削除。
    for path in (MONITOR_CSV, STATUS_CSV):
        if path.exists():
            path.unlink()

    pending = list(JOB_SPECS)
    running: dict[str, RunningJob] = {}
    finished: list[dict[str, object]] = []

    monitor_fields = [
        "timestamp_utc",
        "total_mib",
        "used_mib",
        "free_mib",
        "gpu_util_percent",
        "temperature_c",
        "power_w",
        "running_jobs",
        "reserved_job_budget_mib",
    ]

    status_fields = [
        "model",
        "status",
        "exit_code",
        "elapsed_seconds",
        "budget_mib",
        "log_path",
    ]

    print(
        "scheduler_start",
        f"rolling_points={args.rolling_points}",
        f"max_workers={args.max_workers}",
        f"reserve_mib={args.reserve_mib}",
        flush=True,
    )

    while pending or running:
        gpu = query_gpu()

        # 終了したプロセスを回収。
        for model, job in list(running.items()):
            exit_code = job.process.poll()

            if exit_code is None:
                continue

            elapsed = time.monotonic() - job.started_at

            job.log_handle.close()

            status = "PASS" if exit_code == 0 else "FAIL"

            row = {
                "model": model,
                "status": status,
                "exit_code": exit_code,
                "elapsed_seconds": round(
                    elapsed,
                    3,
                ),
                "budget_mib": (job.spec.budget_mib),
                "log_path": str(job.log_path.relative_to(ROOT)),
            }

            finished.append(row)

            append_csv(
                STATUS_CSV,
                status_fields,
                row,
            )

            print(
                "finished",
                model,
                status,
                f"exit={exit_code}",
                f"elapsed={elapsed:.2f}s",
                flush=True,
            )

            del running[model]

        reserved_running = sum(job.spec.budget_mib for job in running.values())

        # 空きVRAMとworker上限の両方を満たす限り投入。
        launched = True

        while launched and pending and len(running) < args.max_workers:
            launched = False

            gpu = query_gpu()

            usable_free = gpu["free_mib"] - args.reserve_mib

            # pending内で現在投入可能な最大予算モデルを選ぶ。
            candidates = [spec for spec in pending if spec.budget_mib <= usable_free]

            if not candidates:
                break

            spec = max(
                candidates,
                key=lambda item: item.budget_mib,
            )

            job = start_job(
                spec,
                args.rolling_points,
            )

            running[spec.job_id] = job
            pending.remove(spec)

            print(
                "launched",
                spec.job_id,
                f"pid={job.process.pid}",
                f"budget={spec.budget_mib}MiB",
                f"gpu_free={gpu['free_mib']:.0f}MiB",
                flush=True,
            )

            # CUDA context生成直後の急増を待つ。
            time.sleep(2.0)
            launched = True

        gpu = query_gpu()

        append_csv(
            MONITOR_CSV,
            monitor_fields,
            {
                "timestamp_utc": (datetime.now(UTC).isoformat()),
                **gpu,
                "running_jobs": ",".join(sorted(running)),
                "reserved_job_budget_mib": sum(job.spec.budget_mib for job in running.values()),
            },
        )

        print(
            "monitor",
            f"running={','.join(sorted(running)) or '-'}",
            f"pending={','.join(spec.model for spec in pending) or '-'}",
            f"used={gpu['used_mib']:.0f}MiB",
            f"free={gpu['free_mib']:.0f}MiB",
            f"util={gpu['gpu_util_percent']:.0f}%",
            flush=True,
        )

        if pending and not running:
            smallest = min(
                pending,
                key=lambda item: item.budget_mib,
            )

            if gpu["free_mib"] - args.reserve_mib < smallest.budget_mib:
                raise RuntimeError(
                    "No job can be scheduled: "
                    f"free={gpu['free_mib']} MiB, "
                    f"reserve={args.reserve_mib} MiB, "
                    f"smallest_job="
                    f"{smallest.model}:"
                    f"{smallest.budget_mib} MiB"
                )

        time.sleep(args.poll_seconds)

    failed = [row for row in finished if row["status"] != "PASS"]

    print()
    print("scheduler_finished")
    print("jobs=", len(finished))
    print("passed=", len(finished) - len(failed))
    print("failed=", len(failed))
    print("gpu_monitor=", MONITOR_CSV)
    print("status=", STATUS_CSV)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
