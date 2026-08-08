from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from loto.moirai2_campaign.lock_review import (
    LockReviewError,
    validate_installed_review,
)


class RuntimePreflightError(RuntimeError):
    pass


REQUIRED_DEPENDENCIES = {
    "uni2ts": "2.0.0",
    "gluonts": "0.14.4",
    "huggingface-hub": "0.36.2",
    "numpy": "1.26.4",
    "pandas": "2.2.3",
}
REQUIRED_SNAPSHOT_FILES = ("config.json", "model.safetensors")
PROBE_VERSION_KEYS = {
    "uni2ts": "uni2ts_version",
    "gluonts": "gluonts_version",
    "huggingface-hub": "huggingface_hub_version",
    "numpy": "numpy_version",
    "pandas": "pandas_version",
    "torch": "torch_version",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_exact_dependencies(pyproject_path: Path) -> dict[str, str]:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise RuntimePreflightError("pyproject project table is missing")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list):
        raise RuntimePreflightError("pyproject dependencies are missing")
    parsed: dict[str, str] = {}
    for raw in dependencies:
        if not isinstance(raw, str) or "==" not in raw:
            raise RuntimePreflightError(f"dependency is not exactly pinned: {raw!r}")
        name, version = raw.split("==", 1)
        parsed[name.strip().lower()] = version.strip()
    return parsed


def parse_lock_versions(lock_path: Path) -> dict[str, set[str]]:
    payload = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = payload.get("package")
    if not isinstance(packages, list):
        raise RuntimePreflightError("uv.lock package entries are missing")
    versions: dict[str, set[str]] = {}
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions.setdefault(name.lower(), set()).add(version)
    return versions


def validate_lane_files(
    environment_path: Path,
    snapshot_path: Path,
    *,
    runtime_lane: str,
) -> dict[str, Any]:
    pyproject_path = environment_path / "pyproject.toml"
    lock_path = environment_path / "uv.lock"
    if not pyproject_path.is_file():
        raise RuntimePreflightError(f"runtime pyproject is missing: {pyproject_path}")
    try:
        review_evidence = validate_installed_review(
            environment_path=environment_path,
            runtime_lane=runtime_lane,
        )
    except LockReviewError as exc:
        raise RuntimePreflightError(f"reviewed lock validation failed: {exc}") from exc
    if not snapshot_path.is_dir():
        raise RuntimePreflightError(f"snapshot directory is missing: {snapshot_path}")
    missing_snapshot = [
        name for name in REQUIRED_SNAPSHOT_FILES if not (snapshot_path / name).is_file()
    ]
    if missing_snapshot:
        raise RuntimePreflightError(f"snapshot required files are missing: {missing_snapshot}")
    dependencies = parse_exact_dependencies(pyproject_path)
    mismatches = {
        name: {"expected": version, "actual": dependencies.get(name)}
        for name, version in REQUIRED_DEPENDENCIES.items()
        if dependencies.get(name) != version
    }
    if mismatches:
        raise RuntimePreflightError(f"runtime dependency pins differ: {mismatches}")
    lock_versions = parse_lock_versions(lock_path)
    unresolved = {
        name: {"expected": version, "locked": sorted(lock_versions.get(name, set()))}
        for name, version in dependencies.items()
        if version not in lock_versions.get(name, set())
    }
    if unresolved:
        raise RuntimePreflightError(f"uv.lock does not resolve exact pins: {unresolved}")
    return {
        "pyproject_path": str(pyproject_path.resolve()),
        "pyproject_sha256": sha256_file(pyproject_path),
        "lock_path": str(lock_path.resolve()),
        "lock_sha256": sha256_file(lock_path),
        "lock_review": review_evidence,
        "snapshot_path": str(snapshot_path.resolve()),
        "snapshot_files": {
            name: sha256_file(snapshot_path / name) for name in REQUIRED_SNAPSHOT_FILES
        },
        "dependency_pins": dependencies,
        "locked_versions": {
            name: sorted(versions) for name, versions in sorted(lock_versions.items())
        },
    }


def run_frozen_probe(
    *,
    environment_path: Path,
    requested_device: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimePreflightError("uv executable is not available")
    dependencies = parse_exact_dependencies(environment_path / "pyproject.toml")
    probe = """
import importlib.metadata
import json
import os
import sys
import torch
payload = {
    "python_executable": sys.executable,
    "python_version": sys.version,
    "uni2ts_version": importlib.metadata.version("uni2ts"),
    "gluonts_version": importlib.metadata.version("gluonts"),
    "huggingface_hub_version": importlib.metadata.version("huggingface-hub"),
    "numpy_version": importlib.metadata.version("numpy"),
    "pandas_version": importlib.metadata.version("pandas"),
    "torch_version": importlib.metadata.version("torch"),
    "torch_cuda_available": torch.cuda.is_available(),
    "torch_cuda_device_count": torch.cuda.device_count(),
    "torch_cuda_version": torch.version.cuda,
    "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
}
print(json.dumps(payload, sort_keys=True))
""".strip()
    environment = os.environ.copy()
    if requested_device == "cpu":
        environment["CUDA_VISIBLE_DEVICES"] = ""
    process = subprocess.run(
        [
            uv,
            "run",
            "--frozen",
            "--project",
            str(environment_path),
            "python",
            "-c",
            probe,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip()
        raise RuntimePreflightError(f"frozen runtime probe failed: {message}")
    try:
        payload = json.loads(process.stdout.strip())
    except json.JSONDecodeError as exc:
        raise RuntimePreflightError("frozen runtime probe returned invalid JSON") from exc
    for name, expected in dependencies.items():
        key = PROBE_VERSION_KEYS.get(name)
        if key and payload.get(key) != expected:
            raise RuntimePreflightError(
                f"runtime import version mismatch for {name}: {payload.get(key)}"
            )
    if requested_device == "cuda" and payload.get("torch_cuda_available") is not True:
        raise RuntimePreflightError("CUDA was requested but Torch reports it unavailable")
    if requested_device == "cpu" and payload.get("cuda_visible_devices") != "":
        raise RuntimePreflightError("CPU preflight did not isolate CUDA_VISIBLE_DEVICES")
    return payload
