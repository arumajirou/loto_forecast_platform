from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GpuProcessSample:
    pid: int
    gpu_uuid: str
    used_memory_mib: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_compute_apps_csv(text: str) -> list[GpuProcessSample]:
    samples: list[GpuProcessSample] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("No running processes found"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            raise ValueError(f"invalid nvidia-smi row {line_number}: {raw_line!r}")
        pid_text, gpu_uuid, memory_text = parts
        samples.append(
            GpuProcessSample(
                pid=int(pid_text),
                gpu_uuid=gpu_uuid,
                used_memory_mib=int(memory_text),
            )
        )
    return samples


def samples_for_pid(samples: list[GpuProcessSample], pid: int) -> list[GpuProcessSample]:
    return [sample for sample in samples if sample.pid == pid]


def summarize_pid_samples(samples: list[GpuProcessSample], pid: int) -> dict[str, object]:
    matched = samples_for_pid(samples, pid)
    if not matched:
        return {
            "provider_pid": pid,
            "captured": False,
            "capture_count": 0,
            "gpu_uuid": None,
            "max_gpu_memory_mib": 0,
            "min_gpu_memory_mib": 0,
        }
    uuids = {sample.gpu_uuid for sample in matched}
    if len(uuids) != 1:
        raise ValueError(f"provider PID {pid} appeared on multiple GPU UUIDs: {sorted(uuids)}")
    memory = [sample.used_memory_mib for sample in matched]
    return {
        "provider_pid": pid,
        "captured": True,
        "capture_count": len(matched),
        "gpu_uuid": next(iter(uuids)),
        "max_gpu_memory_mib": max(memory),
        "min_gpu_memory_mib": min(memory),
    }
