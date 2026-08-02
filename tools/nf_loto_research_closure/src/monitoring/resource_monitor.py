"""
学習実行時の CPU / メモリ / GPU / ディスク IO などのスナップショットを取得するモジュール。
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from typing import Any, Dict, Optional

import psutil

try:
    import torch
except Exception:  # pragma: no cover - torch が入っていない環境でも動くように
    torch = None  # type: ignore[assignment]


def _get_gpu_info() -> Optional[Dict[str, Any]]:
    if torch is None or not hasattr(torch, "cuda") or not torch.cuda.is_available():
        return None
    try:
        idx = 0
        props = torch.cuda.get_device_properties(idx)
        mem_alloc = torch.cuda.memory_allocated(idx)
        mem_reserved = torch.cuda.memory_reserved(idx)
        return {
            "name": props.name,
            "total_memory": props.total_memory,
            "memory_allocated": mem_alloc,
            "memory_reserved": mem_reserved,
        }
    except Exception:
        return None


def collect_resource_snapshot() -> Dict[str, Any]:
    """現在のリソース状況を辞書で返す。JSONB として nf_model_runs.resource_summary に保存する想定。"""
    vm = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    disk = psutil.disk_usage(os.getcwd())
    process = psutil.Process(os.getpid())

    gpu_info = _get_gpu_info()

    snapshot: Dict[str, Any] = {
        "timestamp": time.time(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count(logical=True),
            "process_percent": process.cpu_percent(interval=None),
        },
        "memory": {
            "total": vm.total,
            "available": vm.available,
            "used": vm.used,
            "percent": vm.percent,
            "rss": process.memory_info().rss,
            "vms": process.memory_info().vms,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
    }

    if gpu_info is not None:
        snapshot["gpu"] = gpu_info

    return snapshot
