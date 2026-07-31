"""Structured event logging and lightweight process/resource sampling."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.data.lineage import atomic_write_json


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JsonEventLogger:
    path: Path
    run_id: str
    context: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def emit(self, event: str, *, status: str | None = None, **fields: Any) -> dict[str, Any]:
        payload = {
            "timestamp": now_iso(),
            "run_id": self.run_id,
            "event": event,
            **self.context,
            **fields,
        }
        if status is not None:
            payload["status"] = status
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return payload


def _process_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    try:
        import psutil

        proc = psutil.Process()
        memory = proc.memory_info()
        result.update(
            {
                "cpu_percent": proc.cpu_percent(interval=None),
                "rss_bytes": int(memory.rss),
                "vms_bytes": int(memory.vms),
                "threads": proc.num_threads(),
                "children": [child.pid for child in proc.children(recursive=True)],
            }
        )
    except Exception as exc:
        result["psutil_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _gpu_snapshot() -> dict[str, Any]:
    query = "timestamp,index,uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    try:
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"available": False, "returncode": proc.returncode, "stderr": proc.stderr[-500:]}
    rows = []
    for line in proc.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) >= 9:
            rows.append(
                {
                    "timestamp": parts[0],
                    "index": parts[1],
                    "uuid": parts[2],
                    "name": parts[3],
                    "utilization_gpu_percent": parts[4],
                    "memory_used_mib": parts[5],
                    "memory_total_mib": parts[6],
                    "temperature_c": parts[7],
                    "power_w": parts[8],
                }
            )
    return {"available": bool(rows), "gpus": rows}


@dataclass
class ResourceMonitor:
    output_path: Path
    interval_seconds: float = 2.0
    capture_gpu: bool = True
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _samples: int = field(default=0, init=False)

    def start(self) -> ResourceMonitor:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="loto-resource-monitor", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            payload = {"timestamp": now_iso(), "process": _process_snapshot()}
            if self.capture_gpu:
                payload["gpu"] = _gpu_snapshot()
            with self.output_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._samples += 1
            self._stop.wait(self.interval_seconds)

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_seconds * 2))
        summary = {
            "path": str(self.output_path),
            "samples": self._samples,
            "stopped_at": now_iso(),
        }
        atomic_write_json(self.output_path.with_suffix(".summary.json"), summary)
        return summary

    def __enter__(self) -> ResourceMonitor:
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()
