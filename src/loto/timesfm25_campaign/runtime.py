from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class NvidiaProcessEvidence:
    external_pid_match: bool
    gpu_uuid: str | None
    used_memory_bytes: int


def query_nvidia_process(pid: int | None = None) -> NvidiaProcessEvidence:
    target_pid = os.getpid() if pid is None else pid
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,gpu_uuid,used_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return NvidiaProcessEvidence(False, None, 0)
    if result.returncode != 0:
        return NvidiaProcessEvidence(False, None, 0)
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            observed_pid = int(parts[0])
            used_memory_bytes = int(parts[2]) * 1024 * 1024
        except ValueError:
            continue
        if observed_pid == target_pid:
            return NvidiaProcessEvidence(True, parts[1] or None, used_memory_bytes)
    return NvidiaProcessEvidence(False, None, 0)
