from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CheckStatus = Literal["PASS", "BLOCKED", "FAIL", "SKIPPED"]
OverallStatus = Literal["PASS", "BLOCKED", "FAIL"]


class RuntimePreflightError(RuntimeError):
    """Base error for runtime preflight contract violations."""


class RuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile_name: str = Field(min_length=1)
    python_min: tuple[int, int] = (3, 10)
    python_max_exclusive: tuple[int, int] = (3, 14)
    package_versions: dict[str, str]
    required_imports: tuple[str, ...]
    required_model_exports: tuple[str, ...]
    optional_imports: tuple[str, ...] = ()
    lockfile_path: str
    require_cuda: bool = False
    require_nvidia_smi: bool = False
    allow_cpu_fallback: bool = False
    allow_network: bool = False
    smoke_models: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=120, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_profile(self) -> RuntimeProfile:
        if self.python_min >= self.python_max_exclusive:
            raise ValueError("python_min must be lower than python_max_exclusive")
        if self.package_versions.get("darts") != "0.46.1":
            raise ValueError("runtime profile must pin darts==0.46.1")
        if len(set(self.required_imports)) != len(self.required_imports):
            raise ValueError("required_imports must be unique")
        if len(set(self.required_model_exports)) != len(self.required_model_exports):
            raise ValueError("required_model_exports must be unique")
        if len(set(self.smoke_models)) != len(self.smoke_models):
            raise ValueError("smoke_models must be unique")
        if self.require_cuda and self.allow_cpu_fallback:
            raise ValueError("CUDA profiles cannot allow CPU fallback")
        if self.require_nvidia_smi and not self.require_cuda:
            raise ValueError("nvidia-smi evidence requires CUDA")
        path = Path(self.lockfile_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("lockfile_path must be repository-relative")
        return self


class RuntimeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(min_length=1)
    status: CheckStatus
    required: bool
    expected: Any = None
    observed: Any = None
    detail: str = ""


class RuntimePreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile_name: str
    overall_status: OverallStatus
    checks: tuple[RuntimeCheck, ...]
    python_executable: str
    process_id: int = Field(ge=1)
    platform: str
    report_sha256: str


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _overall_status(checks: Sequence[RuntimeCheck]) -> OverallStatus:
    required = [item for item in checks if item.required]
    if any(item.status == "FAIL" for item in required):
        return "FAIL"
    if any(item.status in {"BLOCKED", "SKIPPED"} for item in required):
        return "BLOCKED"
    return "PASS"


def _python_check(
    profile: RuntimeProfile,
    version_info: tuple[int, int],
) -> RuntimeCheck:
    within_range = profile.python_min <= version_info < profile.python_max_exclusive
    return RuntimeCheck(
        check_id="python_version",
        status="PASS" if within_range else "FAIL",
        required=True,
        expected={
            "min": profile.python_min,
            "max_exclusive": profile.python_max_exclusive,
        },
        observed=version_info,
        detail="Python version is inside the supported runtime interval"
        if within_range
        else "Python version is outside the supported runtime interval",
    )


def _lockfile_check(profile: RuntimeProfile, repository_root: Path) -> RuntimeCheck:
    path = repository_root / profile.lockfile_path
    if not path.is_file():
        return RuntimeCheck(
            check_id="lockfile",
            status="BLOCKED",
            required=True,
            expected=profile.lockfile_path,
            observed=None,
            detail="uv.lock is missing; dependency resolution is not certified",
        )
    return RuntimeCheck(
        check_id="lockfile",
        status="PASS",
        required=True,
        expected=profile.lockfile_path,
        observed={"size_bytes": path.stat().st_size, "sha256": file_sha256(path)},
        detail="lockfile exists and has a stable SHA-256",
    )


def _package_checks(
    profile: RuntimeProfile,
    version_getter: Callable[[str], str],
) -> list[RuntimeCheck]:
    checks: list[RuntimeCheck] = []
    for package_name, expected_version in sorted(profile.package_versions.items()):
        try:
            observed = version_getter(package_name)
        except importlib.metadata.PackageNotFoundError:
            checks.append(
                RuntimeCheck(
                    check_id=f"package:{package_name}",
                    status="BLOCKED",
                    required=True,
                    expected=expected_version,
                    observed=None,
                    detail="package is not installed",
                )
            )
            continue
        except Exception as error:
            checks.append(
                RuntimeCheck(
                    check_id=f"package:{package_name}",
                    status="FAIL",
                    required=True,
                    expected=expected_version,
                    observed=type(error).__name__,
                    detail=str(error),
                )
            )
            continue
        exact = observed == expected_version
        checks.append(
            RuntimeCheck(
                check_id=f"package:{package_name}",
                status="PASS" if exact else "FAIL",
                required=True,
                expected=expected_version,
                observed=observed,
                detail="exact version match" if exact else "installed version differs",
            )
        )
    return checks


def _import_checks(
    profile: RuntimeProfile,
    importer: Callable[[str], Any],
) -> list[RuntimeCheck]:
    checks: list[RuntimeCheck] = []
    for module_name in profile.required_imports:
        try:
            importer(module_name)
        except ModuleNotFoundError as error:
            checks.append(
                RuntimeCheck(
                    check_id=f"import:{module_name}",
                    status="BLOCKED",
                    required=True,
                    expected="import succeeds",
                    observed=error.name,
                    detail=str(error),
                )
            )
        except Exception as error:
            checks.append(
                RuntimeCheck(
                    check_id=f"import:{module_name}",
                    status="FAIL",
                    required=True,
                    expected="import succeeds",
                    observed=type(error).__name__,
                    detail=str(error),
                )
            )
        else:
            checks.append(
                RuntimeCheck(
                    check_id=f"import:{module_name}",
                    status="PASS",
                    required=True,
                    expected="import succeeds",
                    observed="imported",
                    detail="required import succeeded",
                )
            )
    for module_name in profile.optional_imports:
        try:
            importer(module_name)
        except Exception as error:
            checks.append(
                RuntimeCheck(
                    check_id=f"optional_import:{module_name}",
                    status="SKIPPED",
                    required=False,
                    expected="import succeeds when feature is enabled",
                    observed=type(error).__name__,
                    detail=str(error),
                )
            )
        else:
            checks.append(
                RuntimeCheck(
                    check_id=f"optional_import:{module_name}",
                    status="PASS",
                    required=False,
                    expected="optional import",
                    observed="imported",
                    detail="optional import succeeded",
                )
            )
    return checks


def _model_export_checks(
    profile: RuntimeProfile,
    model_namespace: Any | None,
) -> list[RuntimeCheck]:
    if model_namespace is None:
        return [
            RuntimeCheck(
                check_id=f"model_export:{model_name}",
                status="BLOCKED",
                required=True,
                expected=model_name,
                observed=None,
                detail="darts.models namespace is unavailable",
            )
            for model_name in profile.required_model_exports
        ]
    checks: list[RuntimeCheck] = []
    for model_name in profile.required_model_exports:
        available = hasattr(model_namespace, model_name)
        checks.append(
            RuntimeCheck(
                check_id=f"model_export:{model_name}",
                status="PASS" if available else "FAIL",
                required=True,
                expected=model_name,
                observed=model_name if available else None,
                detail="model export is available"
                if available
                else "model export is absent from darts.models",
            )
        )
    return checks


def _parse_nvidia_process_rows(output: str) -> dict[int, int]:
    rows: dict[int, int] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 2:
            raise RuntimePreflightError(f"unexpected nvidia-smi row: {line}")
        rows[int(parts[0])] = int(parts[1])
    return rows


def _cuda_checks(
    profile: RuntimeProfile,
    torch_module: Any | None,
    nvidia_runner: Callable[..., subprocess.CompletedProcess[str]],
    process_id: int,
) -> list[RuntimeCheck]:
    if not profile.require_cuda:
        return [
            RuntimeCheck(
                check_id="cuda_required",
                status="SKIPPED",
                required=False,
                expected=False,
                observed=False,
                detail="profile does not require CUDA",
            )
        ]
    if torch_module is None:
        return [
            RuntimeCheck(
                check_id="cuda_runtime",
                status="BLOCKED",
                required=True,
                expected="torch with CUDA",
                observed=None,
                detail="torch import is unavailable",
            )
        ]
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not bool(cuda.is_available()):
        return [
            RuntimeCheck(
                check_id="cuda_runtime",
                status="BLOCKED",
                required=True,
                expected="CUDA available",
                observed=False,
                detail="CUDA was requested but torch reports unavailable",
            )
        ]
    try:
        device_count = int(cuda.device_count())
        current_device = int(cuda.current_device())
        device_name = str(cuda.get_device_name(current_device))
        tensor = torch_module.ones(1, device=f"cuda:{current_device}")
        cuda.synchronize(current_device)
        tensor_device = str(tensor.device)
        allocated = int(cuda.memory_allocated(current_device))
        reserved = int(cuda.memory_reserved(current_device))
    except Exception as error:
        return [
            RuntimeCheck(
                check_id="cuda_runtime",
                status="FAIL",
                required=True,
                expected="CUDA tensor allocation succeeds",
                observed=type(error).__name__,
                detail=str(error),
            )
        ]
    checks = [
        RuntimeCheck(
            check_id="cuda_runtime",
            status="PASS",
            required=True,
            expected={"device_count_min": 1, "tensor_device_prefix": "cuda"},
            observed={
                "device_count": device_count,
                "current_device": current_device,
                "device_name": device_name,
                "tensor_device": tensor_device,
                "torch_cuda_version": getattr(getattr(torch_module, "version", None), "cuda", None),
                "allocated_bytes": allocated,
                "reserved_bytes": reserved,
            },
            detail="CUDA allocation and synchronization succeeded",
        )
    ]
    if not profile.require_nvidia_smi:
        return checks
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,used_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = nvidia_runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=profile.timeout_seconds,
        )
        process_rows = _parse_nvidia_process_rows(completed.stdout)
    except FileNotFoundError:
        checks.append(
            RuntimeCheck(
                check_id="nvidia_smi_process",
                status="BLOCKED",
                required=True,
                expected=process_id,
                observed=None,
                detail="nvidia-smi is unavailable",
            )
        )
    except Exception as error:
        checks.append(
            RuntimeCheck(
                check_id="nvidia_smi_process",
                status="FAIL",
                required=True,
                expected=process_id,
                observed=type(error).__name__,
                detail=str(error),
            )
        )
    else:
        present = process_id in process_rows
        checks.append(
            RuntimeCheck(
                check_id="nvidia_smi_process",
                status="PASS" if present else "FAIL",
                required=True,
                expected=process_id,
                observed=process_rows,
                detail="current PID appears in nvidia-smi compute process table"
                if present
                else "current PID is absent from nvidia-smi compute process table",
            )
        )
    return checks


def run_runtime_preflight(
    profile: RuntimeProfile,
    repository_root: Path,
    *,
    version_info: tuple[int, int] | None = None,
    version_getter: Callable[[str], str] = importlib.metadata.version,
    importer: Callable[[str], Any] = importlib.import_module,
    nvidia_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    process_id: int | None = None,
) -> RuntimePreflightReport:
    root = repository_root.resolve()
    current_version = version_info or (sys.version_info.major, sys.version_info.minor)
    pid = process_id or os.getpid()
    checks: list[RuntimeCheck] = [_python_check(profile, current_version)]
    checks.append(_lockfile_check(profile, root))
    checks.extend(_package_checks(profile, version_getter))
    checks.extend(_import_checks(profile, importer))
    try:
        model_namespace = importer("darts.models")
    except Exception:
        model_namespace = None
    checks.extend(_model_export_checks(profile, model_namespace))
    try:
        torch_module = importer("torch")
    except Exception:
        torch_module = None
    checks.extend(_cuda_checks(profile, torch_module, nvidia_runner, pid))
    status = _overall_status(checks)
    payload = {
        "schema_version": 1,
        "profile_name": profile.profile_name,
        "overall_status": status,
        "checks": [item.model_dump(mode="json") for item in checks],
        "python_executable": sys.executable,
        "process_id": pid,
        "platform": platform.platform(),
    }
    return RuntimePreflightReport(
        **payload,
        report_sha256=canonical_sha256(payload),
    )


def load_profile(path: Path) -> RuntimeProfile:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RuntimeProfile.model_validate(raw)


def write_report(report: RuntimePreflightReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
