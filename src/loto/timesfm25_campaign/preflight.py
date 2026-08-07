from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from loto.adapters.timesfm25.contracts import TimesFM25Request
from loto.timesfm25_campaign.model_manifest import ModelManifest

CommandRunner = Callable[[list[str], Path, Mapping[str, str], int], dict[str, Any]]
PINNED_DEPENDENCIES = {
    "huggingface-hub": "0.36.2",
    "timesfm": "2.0.2",
    "torch": "2.9.1",
}
OFFLINE_VARIABLES = {
    "HF_HUB_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "UV_OFFLINE": "1",
}


def offline_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    environment.update(OFFLINE_VARIABLES)
    return environment


def _run_command(
    command: list[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int,
) -> dict[str, Any]:
    started = __import__("time").perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": __import__("time").perf_counter() - started,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "duration_seconds": __import__("time").perf_counter() - started,
        }


def _record(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    *,
    required: bool = True,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "required": required,
            "detail": detail,
        }
    )


def _dependency_versions(pyproject_path: Path) -> dict[str, str]:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = payload.get("project", {}).get("dependencies", [])
    versions: dict[str, str] = {}
    for dependency in dependencies:
        normalized = dependency.lower().replace("_", "-")
        name = normalized.split("[", 1)[0].split("==", 1)[0]
        if "==" in normalized:
            versions[name] = normalized.rsplit("==", 1)[1]
    return versions


def _locked_versions(lock_path: Path) -> dict[str, str]:
    payload = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for package in payload.get("package", []):
        name = str(package.get("name", "")).lower().replace("_", "-")
        version = package.get("version")
        if name and isinstance(version, str):
            versions[name] = version
    return versions


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _runtime_probe_command(environment: Path) -> list[str]:
    code = (
        "import importlib.metadata as m,json,torch;"
        "print(json.dumps({'timesfm':m.version('timesfm'),"
        "'torch':m.version('torch'),'huggingface-hub':m.version('huggingface-hub'),"
        "'cuda_available':torch.cuda.is_available(),"
        "'cuda_device_count':torch.cuda.device_count()}))"
    )
    return [
        "uv",
        "run",
        "--project",
        str(environment),
        "--locked",
        "--offline",
        "python",
        "-c",
        code,
    ]


def run_preflight(
    request: TimesFM25Request,
    *,
    environment: Path,
    manifest: ModelManifest,
    project_root: Path,
    require_cuda: bool | None = None,
    timeout: int = 300,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    environment = environment.resolve()
    require_cuda = request.device == "cuda" if require_cuda is None else require_cuda
    execute = _run_command if runner is None else runner
    checks: list[dict[str, Any]] = []
    commands: dict[str, dict[str, Any]] = {}

    backend = manifest.backends.get(request.backend)
    _record(checks, "backend_manifest", backend is not None, request.backend.value)
    if backend is not None:
        _record(checks, "repo_id", request.repo_id == backend.repo_id, request.repo_id)
        _record(checks, "revision", request.revision == backend.revision, request.revision)

    pyproject_path = environment / "pyproject.toml"
    _record(checks, "environment_pyproject", pyproject_path.is_file(), str(pyproject_path))
    if pyproject_path.is_file():
        try:
            declared = _dependency_versions(pyproject_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            declared = {}
            _record(
                checks,
                "environment_pyproject_parse",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        else:
            _record(checks, "environment_pyproject_parse", True, "valid TOML")
        for name, expected in PINNED_DEPENDENCIES.items():
            actual = declared.get(name)
            _record(
                checks,
                f"declared_dependency:{name}",
                actual == expected,
                f"expected={expected};actual={actual}",
            )

    lock_path = environment / "uv.lock"
    _record(checks, "uv_lock_exists", lock_path.is_file(), str(lock_path))
    if lock_path.is_file():
        try:
            locked = _locked_versions(lock_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            locked = {}
            _record(
                checks,
                "uv_lock_parse",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        else:
            _record(checks, "uv_lock_parse", True, "valid TOML")
        for name, expected in PINNED_DEPENDENCIES.items():
            actual = locked.get(name)
            _record(
                checks,
                f"locked_dependency:{name}",
                actual == expected,
                f"expected={expected};actual={actual}",
            )

    uv_path = shutil.which("uv")
    _record(checks, "uv_executable", uv_path is not None, str(uv_path))
    environment_vars = offline_environment()
    if uv_path is not None and lock_path.is_file():
        lock_command = [
            "uv",
            "lock",
            "--check",
            "--offline",
            "--project",
            str(environment),
        ]
        commands["uv_lock_check"] = execute(
            lock_command,
            project_root,
            environment_vars,
            timeout,
        )
        _record(
            checks,
            "uv_lock_check",
            commands["uv_lock_check"].get("returncode") == 0,
            f"returncode={commands['uv_lock_check'].get('returncode')}",
        )

    snapshot = Path(request.snapshot_path).expanduser() if request.snapshot_path else None
    _record(
        checks,
        "snapshot_path_explicit",
        snapshot is not None and snapshot.is_absolute(),
        str(snapshot),
    )
    snapshot_ok = snapshot is not None and snapshot.is_dir()
    _record(checks, "snapshot_directory", snapshot_ok, str(snapshot))
    if snapshot_ok and snapshot is not None:
        config_path = snapshot / "config.json"
        config_valid = False
        if config_path.is_file():
            try:
                config_valid = isinstance(
                    json.loads(config_path.read_text(encoding="utf-8")),
                    dict,
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                config_valid = False
        _record(checks, "snapshot_config_json", config_valid, str(config_path))

        weight_files = sorted(snapshot.glob("*.safetensors"))
        _record(
            checks,
            "snapshot_weight_count",
            len(weight_files) == 1,
            f"count={len(weight_files)}",
        )
        if len(weight_files) == 1 and backend is not None:
            from loto.timesfm25_campaign.certification_bundle import sha256_file

            try:
                actual_hash = sha256_file(weight_files[0])
            except OSError as exc:
                actual_hash = None
                _record(
                    checks,
                    "snapshot_weight_read",
                    False,
                    f"{type(exc).__name__}: {exc}",
                )
            _record(
                checks,
                "snapshot_weight_sha256",
                actual_hash == backend.weight_sha256,
                f"expected={backend.weight_sha256};actual={actual_hash}",
            )

    if uv_path is not None and lock_path.is_file():
        commands["runtime_probe"] = execute(
            _runtime_probe_command(environment),
            project_root,
            environment_vars,
            timeout,
        )
        probe = _last_json_object(str(commands["runtime_probe"].get("stdout", "")))
        _record(
            checks,
            "runtime_probe_exit",
            commands["runtime_probe"].get("returncode") == 0,
            f"returncode={commands['runtime_probe'].get('returncode')}",
        )
        _record(checks, "runtime_probe_json", probe is not None, str(probe))
        if probe is not None:
            for name, expected in PINNED_DEPENDENCIES.items():
                actual = probe.get(name)
                _record(
                    checks,
                    f"runtime_dependency:{name}",
                    actual == expected,
                    f"expected={expected};actual={actual}",
                )
            _record(
                checks,
                "torch_cuda_available",
                not require_cuda or probe.get("cuda_available") is True,
                f"require_cuda={require_cuda};actual={probe.get('cuda_available')}",
            )
            device_count = probe.get("cuda_device_count")
            device_count_valid = isinstance(device_count, int) and device_count > 0
            _record(
                checks,
                "torch_cuda_device_count",
                not require_cuda or device_count_valid,
                f"actual={device_count}",
            )

    nvidia_path = shutil.which("nvidia-smi")
    _record(
        checks,
        "nvidia_smi_executable",
        not require_cuda or nvidia_path is not None,
        str(nvidia_path),
    )
    if nvidia_path is not None:
        command = [
            "nvidia-smi",
            "--query-gpu=uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
        commands["nvidia_smi"] = execute(
            command,
            project_root,
            environment_vars,
            timeout,
        )
        _record(
            checks,
            "nvidia_smi_query",
            not require_cuda or commands["nvidia_smi"].get("returncode") == 0,
            f"returncode={commands['nvidia_smi'].get('returncode')}",
        )

    failed = [check["name"] for check in checks if check["required"] and check["status"] != "PASS"]
    return {
        "schema_version": 1,
        "run_id": request.run_id,
        "status": "PASS" if not failed else "FAIL",
        "backend": request.backend.value,
        "repo_id": request.repo_id,
        "revision": request.revision,
        "device_requested": request.device,
        "require_cuda": require_cuda,
        "project_root": str(project_root),
        "environment": str(environment),
        "snapshot_path": str(snapshot) if snapshot is not None else None,
        "offline_environment": OFFLINE_VARIABLES,
        "checks": checks,
        "failed_checks": failed,
        "commands": commands,
    }
