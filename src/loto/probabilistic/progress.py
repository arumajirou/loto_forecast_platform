from __future__ import annotations

import math
import statistics
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


_RESOURCE_CLASSES = ("gpu", "heavy_cpu", "light_cpu")


def format_duration(seconds: float | int | None) -> str:
    if seconds is None or not math.isfinite(float(seconds)):
        return "--"
    value = max(int(round(float(seconds))), 0)
    days, value = divmod(value, 86400)
    hours, value = divmod(value, 3600)
    minutes, secs = divmod(value, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}日")
    if hours or days:
        parts.append(f"{hours}時間")
    if minutes or hours or days:
        parts.append(f"{minutes}分")
    parts.append(f"{secs}秒")
    return "".join(parts)


def progress_bar(percent: float, width: int = 32) -> str:
    bounded = min(max(float(percent), 0.0), 100.0)
    filled = int(round(width * bounded / 100.0))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def _median_or_default(values: list[float], default: float) -> float:
    valid = [float(value) for value in values if value is not None and float(value) > 0]
    return statistics.median(valid) if valid else float(default)


@dataclass
class ProgressEstimator:
    outer_workers: int
    limits: dict[str, int]
    defaults: dict[str, float]
    started_at_wall: float = field(default_factory=time.time)
    durations: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    running_started: dict[str, float] = field(default_factory=dict)
    running_resource: dict[str, str] = field(default_factory=dict)

    def start(self, trial_id: str, resource_class: str) -> None:
        self.running_started[trial_id] = time.monotonic()
        self.running_resource[trial_id] = resource_class

    def finish(
        self,
        trial_id: str,
        resource_class: str,
        elapsed_seconds: float | int | None,
    ) -> None:
        self.running_started.pop(trial_id, None)
        self.running_resource.pop(trial_id, None)
        if elapsed_seconds is not None and float(elapsed_seconds) > 0:
            self.durations[resource_class].append(float(elapsed_seconds))

    def average_seconds(self, resource_class: str) -> float:
        return _median_or_default(
            self.durations.get(resource_class, []),
            self.defaults.get(resource_class, 60.0),
        )

    def estimate(
        self,
        pending_by_resource: dict[str, int],
        running_trials: dict[str, str],
    ) -> dict[str, Any]:
        now_mono = time.monotonic()
        work_by_resource: dict[str, float] = {}
        average_by_resource: dict[str, float] = {}
        samples_by_resource: dict[str, int] = {}

        for resource in _RESOURCE_CLASSES:
            average = self.average_seconds(resource)
            average_by_resource[resource] = round(average, 1)
            samples_by_resource[resource] = len(self.durations.get(resource, []))
            pending_work = max(int(pending_by_resource.get(resource, 0)), 0) * average
            running_work = 0.0
            for trial_id, trial_resource in running_trials.items():
                if trial_resource != resource:
                    continue
                started = self.running_started.get(trial_id, now_mono)
                elapsed = max(now_mono - started, 0.0)
                running_work += max(average - elapsed, average * 0.10)
            work_by_resource[resource] = pending_work + running_work

        class_eta: dict[str, float] = {}
        for resource, work in work_by_resource.items():
            limit = max(int(self.limits.get(resource, self.outer_workers)), 1)
            class_eta[resource] = work / limit

        total_work = sum(work_by_resource.values())
        global_eta = total_work / max(int(self.outer_workers), 1)
        remaining = max([global_eta, *class_eta.values()], default=0.0)
        completion_at = datetime.now().astimezone() + timedelta(seconds=remaining)
        completed_samples = sum(samples_by_resource.values())
        active_resources = {
            resource
            for resource in _RESOURCE_CLASSES
            if pending_by_resource.get(resource, 0) > 0
            or resource in running_trials.values()
        }
        minimum_samples = min(
            (samples_by_resource[resource] for resource in active_resources),
            default=completed_samples,
        )
        confidence = "low"
        if completed_samples >= 10 and minimum_samples >= 2:
            confidence = "medium"
        if completed_samples >= 30 and minimum_samples >= 5:
            confidence = "high"

        return {
            "estimated_remaining_seconds": round(remaining, 1),
            "estimated_remaining_text": format_duration(remaining),
            "estimated_completion_at": completion_at.isoformat(timespec="seconds"),
            "eta_confidence": confidence,
            "estimated_seconds_by_resource": {
                key: round(value, 1) for key, value in class_eta.items()
            },
            "median_trial_seconds_by_resource": average_by_resource,
            "duration_samples_by_resource": samples_by_resource,
        }


def gpu_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "gpus": [],
        }

    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            continue
        index, name, util, used, total, temperature, power = parts
        try:
            rows.append(
                {
                    "index": int(index),
                    "name": name,
                    "utilization_percent": float(util),
                    "memory_used_mib": float(used),
                    "memory_total_mib": float(total),
                    "temperature_c": float(temperature),
                    "power_w": float(power),
                }
            )
        except ValueError:
            continue
    return {"available": bool(rows), "gpus": rows}


def render_dashboard(progress: dict[str, Any], width: int = 36) -> str:
    completed = int(progress.get("completed_allowed", 0))
    total = int(progress.get("trials_allowed", 0))
    percent = float(progress.get("progress_percent", 0.0))
    counts = progress.get("status_counts") or {}
    running = progress.get("running_trials") or []
    eta = progress.get("eta") or {}
    audit = progress.get("parallelism") or {}
    gpu = progress.get("gpu") or {}

    lines = [
        "=" * 78,
        f"PPL01 {progress.get('status', 'UNKNOWN')}  {progress.get('timestamp', '')}",
        f"{progress_bar(percent, width)} {percent:6.2f}%  {completed}/{total}",
        (
            f"PASS={counts.get('PASS', 0)}  NON-PASS={max(completed - int(counts.get('PASS', 0)), 0)}  "
            f"残り={max(total - completed, 0)}"
        ),
        (
            f"経過={format_duration(progress.get('elapsed_seconds'))}  "
            f"残り予測={eta.get('estimated_remaining_text', '--')}  "
            f"終了予測={eta.get('estimated_completion_at', '--')}  "
            f"信頼度={eta.get('eta_confidence', '--')}"
        ),
        (
            "並列: "
            f"現在={audit.get('running_total', 0)}/{audit.get('outer_workers', 0)}  "
            f"ピーク={audit.get('peak_running_total', 0)}  "
            f"resource={audit.get('running_by_resource', {})}"
        ),
    ]
    if gpu.get("available") and gpu.get("gpus"):
        first = gpu["gpus"][0]
        lines.append(
            "GPU: "
            f"{first.get('name')}  util={first.get('utilization_percent')}%  "
            f"VRAM={first.get('memory_used_mib')}/{first.get('memory_total_mib')} MiB  "
            f"temp={first.get('temperature_c')}C"
        )
    else:
        lines.append(f"GPU: unavailable ({gpu.get('error', 'not detected')})")
    lines.append("実行中:")
    if running:
        lines.extend(f"  - {trial_id}" for trial_id in running[:12])
        if len(running) > 12:
            lines.append(f"  ... and {len(running) - 12} more")
    else:
        lines.append("  なし")
    best = progress.get("best_model") or {}
    if best:
        lines.append(
            "暫定最良: "
            f"{best.get('model_id')}  ±1={best.get('hit_at_1')}  "
            f"MAE={best.get('mae')}  MSE={best.get('mse')}"
        )
    lines.append(f"run_dir: {progress.get('run_dir', '')}")
    lines.append("=" * 78)
    return "\n".join(lines)


__all__ = [
    "ProgressEstimator",
    "format_duration",
    "gpu_snapshot",
    "progress_bar",
    "render_dashboard",
]
