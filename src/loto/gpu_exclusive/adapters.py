"""External runtime, request-gate, and NVIDIA GPU adapters."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import ExternalGateConfig, GpuProbeConfig, HttpRuntimeConfig


class AdapterError(RuntimeError):
    """Raised when an external control-plane dependency violates its contract."""


def _request(url: str, *, method: str, timeout: float) -> tuple[int, str]:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local operator URLs
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AdapterError(f"{method} {url} failed: {exc}") from exc


@dataclass(frozen=True)
class RuntimeIdentitySnapshot:
    running: bool
    body: str
    body_sha256: str


class HttpRuntime:
    def __init__(self, config: HttpRuntimeConfig) -> None:
        self.config = config

    def identity_snapshot(self) -> RuntimeIdentitySnapshot:
        try:
            status, body = _request(
                self.config.running_url,
                method="GET",
                timeout=self.config.timeout_seconds,
            )
        except AdapterError:
            return RuntimeIdentitySnapshot(running=False, body="", body_sha256="")
        running = 200 <= status < 300 and self.config.running_contains in body
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return RuntimeIdentitySnapshot(running=running, body=body, body_sha256=digest)

    def running(self) -> bool:
        return self.identity_snapshot().running

    def start(self) -> None:
        status, _ = _request(
            self.config.start_url,
            method=self.config.start_method,
            timeout=self.config.timeout_seconds,
        )
        if not 200 <= status < 300:
            raise AdapterError(f"runtime start returned HTTP {status}")

    def stop(self) -> None:
        status, _ = _request(
            self.config.stop_url,
            method=self.config.stop_method,
            timeout=self.config.timeout_seconds,
        )
        if not 200 <= status < 300:
            raise AdapterError(f"runtime stop returned HTTP {status}")

    def wait_running(self, expected: bool) -> None:
        deadline = time.monotonic() + self.config.transition_timeout_seconds
        while time.monotonic() < deadline:
            if self.running() is expected:
                return
            time.sleep(self.config.poll_interval_seconds)
        raise AdapterError(f"runtime did not reach running={expected}")


class ExternalGate:
    def __init__(self, config: ExternalGateConfig) -> None:
        self.config = config

    def _post(self, url: str) -> None:
        status, _ = _request(url, method="POST", timeout=self.config.timeout_seconds)
        if not 200 <= status < 300:
            raise AdapterError(f"gate POST {url} returned HTTP {status}")

    def _status(self) -> dict[str, object]:
        status, body = _request(
            self.config.status_url,
            method="GET",
            timeout=self.config.timeout_seconds,
        )
        if not 200 <= status < 300:
            raise AdapterError(f"gate status returned HTTP {status}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterError("gate status is not JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterError("gate status JSON is not an object")
        return payload

    def status(self) -> dict[str, object]:
        """Return the live gate state without changing admission control."""

        return self._status()

    def drain_and_close(self) -> None:
        self._post(self.config.quiesce_url)
        deadline = time.monotonic() + self.config.drain_timeout_seconds
        while time.monotonic() < deadline:
            payload = self._status()
            raw = payload.get(self.config.in_flight_field)
            if isinstance(raw, int) and raw == 0:
                self._post(self.config.close_url)
                return
            time.sleep(self.config.poll_interval_seconds)
        raise AdapterError("request gate did not drain to exact zero in-flight requests")

    def open(self) -> None:
        self._post(self.config.open_url)


@dataclass(frozen=True)
class GpuSnapshot:
    index: int
    uuid: str
    memory_used_mib: int
    memory_free_mib: int
    memory_total_mib: int


@dataclass(frozen=True)
class GpuProcessSnapshot:
    gpu_uuid: str
    pid: int
    process_name: str
    used_memory_mib: int | None


class NvidiaSmiProbe:
    def __init__(self, config: GpuProbeConfig) -> None:
        self.config = config

    def snapshot(self) -> GpuSnapshot:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,memory.used,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) != 5:
                continue
            index = int(fields[0])
            if index == self.config.index:
                return GpuSnapshot(
                    index=index,
                    uuid=fields[1],
                    memory_used_mib=int(fields[2]),
                    memory_free_mib=int(fields[3]),
                    memory_total_mib=int(fields[4]),
                )
        raise AdapterError(f"nvidia-smi did not report GPU index {self.config.index}")

    def processes(self, *, gpu_uuid: str | None = None) -> list[GpuProcessSnapshot]:
        target_uuid = gpu_uuid or self.snapshot().uuid
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        rows: list[GpuProcessSnapshot] = []
        for line in result.stdout.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) != 4 or fields[0] != target_uuid:
                continue
            used: int | None
            try:
                used = int(fields[3])
            except ValueError:
                used = None
            rows.append(
                GpuProcessSnapshot(
                    gpu_uuid=fields[0],
                    pid=int(fields[1]),
                    process_name=fields[2],
                    used_memory_mib=used,
                )
            )
        return rows

    def wait_free(self) -> GpuSnapshot:
        deadline = time.monotonic() + self.config.free_timeout_seconds
        stable = 0
        latest: GpuSnapshot | None = None
        while time.monotonic() < deadline:
            latest = self.snapshot()
            if latest.memory_used_mib <= self.config.max_memory_used_mib_when_free:
                stable += 1
                if stable >= self.config.stable_samples:
                    return latest
            else:
                stable = 0
            time.sleep(self.config.poll_interval_seconds)
        raise AdapterError(
            "GPU did not become stably free below "
            f"{self.config.max_memory_used_mib_when_free} MiB; latest={latest}"
        )

    def wait_for_baseline(
        self,
        *,
        baseline: GpuSnapshot,
        baseline_pids: set[int],
        tolerance_mib: int,
    ) -> GpuSnapshot:
        deadline = time.monotonic() + self.config.free_timeout_seconds
        stable = 0
        latest: GpuSnapshot | None = None
        while time.monotonic() < deadline:
            latest = self.snapshot()
            current_pids = {process.pid for process in self.processes(gpu_uuid=baseline.uuid)}
            memory_ok = latest.memory_used_mib <= baseline.memory_used_mib + tolerance_mib
            pids_ok = current_pids == baseline_pids
            if memory_ok and pids_ok:
                stable += 1
                if stable >= self.config.stable_samples:
                    return latest
            else:
                stable = 0
            time.sleep(self.config.poll_interval_seconds)
        raise AdapterError(
            "GPU did not return to coexist baseline; "
            f"baseline_used={baseline.memory_used_mib}, latest={latest}, "
            f"baseline_pids={sorted(baseline_pids)}"
        )
