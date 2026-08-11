from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProcessTreeNode:
    pid: int
    ppid: int | None
    name: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"pid": self.pid, "ppid": self.ppid, "name": self.name}


@dataclass(frozen=True)
class ProcessObservation:
    child_pid: int
    process_tree: tuple[ProcessTreeNode, ...]
    peak_rss_mib: float | None
    gpu_pids: tuple[int, ...]
    peak_gpu_memory_mib: float | None
    gpu_peak_memory_by_pid_mib: dict[int, float]
    gpu_attribution_available: bool
    sample_count: int
    gpu_sample_count: int
    timed_out: bool
    returncode: int | None
    started_at: float
    ended_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_pid": self.child_pid,
            "process_tree": [node.to_dict() for node in self.process_tree],
            "peak_rss_mib": self.peak_rss_mib,
            "gpu_pids": list(self.gpu_pids),
            "peak_gpu_memory_mib": self.peak_gpu_memory_mib,
            "gpu_peak_memory_by_pid_mib": {
                str(pid): value for pid, value in sorted(self.gpu_peak_memory_by_pid_mib.items())
            },
            "gpu_attribution_available": self.gpu_attribution_available,
            "sample_count": self.sample_count,
            "gpu_sample_count": self.gpu_sample_count,
            "timed_out": self.timed_out,
            "returncode": self.returncode,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": max(0.0, self.ended_at - self.started_at),
        }


@dataclass(frozen=True)
class MonitoredProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    observation: ProcessObservation


def _sample_process_tree(root_pid: int) -> tuple[list[ProcessTreeNode], float | None]:
    try:
        import psutil
    except ImportError:
        return [ProcessTreeNode(pid=root_pid, ppid=None, name=None)], None

    try:
        root = psutil.Process(root_pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return [ProcessTreeNode(pid=root_pid, ppid=None, name=None)], None

    nodes: list[ProcessTreeNode] = []
    rss_bytes = 0
    observed_rss = False
    for process in processes:
        try:
            nodes.append(
                ProcessTreeNode(
                    pid=int(process.pid),
                    ppid=int(process.ppid()),
                    name=str(process.name()),
                )
            )
            rss_bytes += int(process.memory_info().rss)
            observed_rss = True
        except psutil.Error:
            continue
    if not nodes:
        nodes.append(ProcessTreeNode(pid=root_pid, ppid=None, name=None))
    rss_mib = rss_bytes / 1024**2 if observed_rss else None
    return nodes, rss_mib


def _query_gpu_process_memory(
    process_pids: set[int],
) -> tuple[bool, set[int], dict[int, float]]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, set(), {}
    if proc.returncode != 0:
        return False, set(), {}

    matched_pids: set[int] = set()
    matched_memory: dict[int, float] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            pid_text, memory_text = line.split(",", maxsplit=1)
            pid = int(pid_text.strip())
        except (ValueError, TypeError):
            continue
        if pid not in process_pids:
            continue
        matched_pids.add(pid)
        try:
            matched_memory[pid] = float(memory_text.strip())
        except (ValueError, TypeError):
            # WSL may expose the compute PID while reporting used_memory as N/A.
            continue
    return True, matched_pids, matched_memory


def _terminate_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        proc.kill()
    proc.wait(timeout=5)


def run_monitored_process(
    command: Sequence[str],
    *,
    cwd: str | Path,
    timeout: float,
    poll_interval: float = 0.2,
    on_start: Callable[[int], None] | None = None,
) -> MonitoredProcessResult:
    """Run a child process while retaining process/RSS/GPU attribution evidence."""

    if timeout <= 0:
        raise ValueError("timeout must be > 0")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be > 0")

    started_at = time.time()
    started_monotonic = time.monotonic()
    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_file:
        proc = subprocess.Popen(
            list(command),
            cwd=Path(cwd),
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=os.name == "posix",
        )
        if on_start is not None:
            on_start(proc.pid)

        observed_nodes: dict[int, ProcessTreeNode] = {
            proc.pid: ProcessTreeNode(pid=proc.pid, ppid=os.getpid(), name=None)
        }
        peak_rss_mib: float | None = None
        gpu_pids: set[int] = set()
        gpu_peak_by_pid: dict[int, float] = {}
        peak_gpu_memory_mib: float | None = None
        gpu_attribution_available = False
        sample_count = 0
        gpu_sample_count = 0
        timed_out = False

        while True:
            nodes, rss_mib = _sample_process_tree(proc.pid)
            sample_count += 1
            for node in nodes:
                observed_nodes[node.pid] = node
            if rss_mib is not None:
                peak_rss_mib = rss_mib if peak_rss_mib is None else max(peak_rss_mib, rss_mib)

            process_pids = set(observed_nodes)
            gpu_available, matched_gpu_pids, gpu_memory = _query_gpu_process_memory(process_pids)
            gpu_attribution_available = gpu_attribution_available or gpu_available
            if gpu_available:
                gpu_sample_count += 1
            gpu_pids.update(matched_gpu_pids)
            if gpu_memory:
                total_gpu_memory = sum(gpu_memory.values())
                peak_gpu_memory_mib = (
                    total_gpu_memory
                    if peak_gpu_memory_mib is None
                    else max(peak_gpu_memory_mib, total_gpu_memory)
                )
                for pid, memory in gpu_memory.items():
                    gpu_peak_by_pid[pid] = max(gpu_peak_by_pid.get(pid, 0.0), memory)

            returncode = proc.poll()
            if returncode is not None:
                break
            if time.monotonic() - started_monotonic >= timeout:
                timed_out = True
                _terminate_process_tree(proc)
                returncode = proc.poll()
                break
            time.sleep(poll_interval)

        ended_at = time.time()
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().decode("utf-8", errors="replace")
        stderr = stderr_file.read().decode("utf-8", errors="replace")

    observation = ProcessObservation(
        child_pid=proc.pid,
        process_tree=tuple(observed_nodes[pid] for pid in sorted(observed_nodes)),
        peak_rss_mib=peak_rss_mib,
        gpu_pids=tuple(sorted(gpu_pids)),
        peak_gpu_memory_mib=peak_gpu_memory_mib,
        gpu_peak_memory_by_pid_mib=gpu_peak_by_pid,
        gpu_attribution_available=gpu_attribution_available,
        sample_count=sample_count,
        gpu_sample_count=gpu_sample_count,
        timed_out=timed_out,
        returncode=returncode,
        started_at=started_at,
        ended_at=ended_at,
    )
    return MonitoredProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        observation=observation,
    )
