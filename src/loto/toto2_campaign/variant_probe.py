from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TOTO2_22M_REPO_ID = "Datadog/Toto-2.0-22m"
TOTO2_22M_REVISION = "3affccf372ff82f5d200ac76fad3dbcdeb64299a"
TOTO2_22M_WEIGHT_SHA256 = "9cd503d82df3aa71747862688f47a31c1d0a4b80f898df6e046189016eaa21dd"
TOTO2_22M_WEIGHT_SIZE_BYTES = 87_669_368
TOTO2_22M_REQUIRED_FILES = (
    ".gitattributes",
    "README.md",
    "config.json",
    "model.safetensors",
)


class VariantProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileDigest:
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class GpuProcessEvidence:
    pid: int
    gpu_uuid: str
    used_gpu_memory_mib: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_snapshot(snapshot_path: Path) -> dict[str, Any]:
    snapshot = snapshot_path.expanduser().resolve(strict=True)
    if not snapshot.is_dir():
        raise VariantProbeError(f"snapshot is not a directory: {snapshot}")
    if snapshot.name != TOTO2_22M_REVISION:
        raise VariantProbeError(
            f"snapshot revision mismatch: expected {TOTO2_22M_REVISION}, got {snapshot.name}"
        )

    files: dict[str, dict[str, object]] = {}
    for name in TOTO2_22M_REQUIRED_FILES:
        path = snapshot / name
        if not path.is_file():
            raise VariantProbeError(f"required snapshot file missing: {name}")
        record = FileDigest(name=name, sha256=sha256_file(path), size_bytes=path.stat().st_size)
        files[name] = asdict(record)

    weight = files["model.safetensors"]
    if weight["sha256"] != TOTO2_22M_WEIGHT_SHA256:
        raise VariantProbeError("22M model.safetensors SHA-256 differs from the reviewed pin")
    if weight["size_bytes"] != TOTO2_22M_WEIGHT_SIZE_BYTES:
        raise VariantProbeError("22M model.safetensors size differs from the reviewed pin")

    return {
        "repo_id": TOTO2_22M_REPO_ID,
        "revision": TOTO2_22M_REVISION,
        "snapshot_path": str(snapshot),
        "files": files,
    }


def parse_nvidia_compute_apps(text: str, *, pid: int) -> list[GpuProcessEvidence]:
    matches: list[GpuProcessEvidence] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            continue
        try:
            observed_pid = int(fields[0])
            used_mib = int(fields[2])
        except ValueError:
            continue
        if observed_pid != pid:
            continue
        if not fields[1] or used_mib <= 0:
            continue
        matches.append(
            GpuProcessEvidence(
                pid=observed_pid,
                gpu_uuid=fields[1],
                used_gpu_memory_mib=used_mib,
            )
        )
    return matches


def capture_gpu_process(pid: int) -> GpuProcessEvidence:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise VariantProbeError(f"nvidia-smi failed: {completed.stderr.strip()}")
    matches = parse_nvidia_compute_apps(completed.stdout, pid=pid)
    if len(matches) != 1:
        raise VariantProbeError(
            f"expected exactly one positive-VRAM GPU record for pid {pid}, observed {len(matches)}"
        )
    return matches[0]


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VariantProbeError(f"expected JSON object: {path}")
    return payload
