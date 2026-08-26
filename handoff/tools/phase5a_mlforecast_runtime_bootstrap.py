#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
SOURCE_WT = Path(
    os.environ.get(
        "LOTO_SOURCE_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248",
    )
)
EXPECTED_SOURCE_SHA = "0a13c287e0f0fcc8f983be3512654524dad18b2c"
RUNTIME = ROOT / ".runtime-envs" / "phase5a-mlforecast-py313"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / f"phase5a-mlforecast-runtime-bootstrap-{RUN_ID}"
PROJECT = OUT / "runtime-project"
SUMMARY = OUT / "summary.json"

CRITICAL_PACKAGES = (
    "mlforecast",
    "optuna",
    "numpy",
    "pandas",
    "pydantic",
    "scikit-learn",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_output(root: Path, args: list[str]) -> str:
    p = run(["git", "-C", str(root), *args], timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def source_gate() -> dict[str, Any]:
    head = git_output(SOURCE_WT, ["rev-parse", "HEAD"])
    if head != EXPECTED_SOURCE_SHA:
        raise RuntimeError(
            f"SOURCE_SHA_GATE_FAILED:expected={EXPECTED_SOURCE_SHA}:actual={head}"
        )
    if git_output(SOURCE_WT, ["status", "--porcelain"]):
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")

    pyproject = SOURCE_WT / "pyproject.toml"
    uv_lock = SOURCE_WT / "uv.lock"
    if not pyproject.is_file() or not uv_lock.is_file():
        raise RuntimeError("SOURCE_DEPENDENCY_CONTRACT_MISSING")

    return {
        "source_sha": head,
        "pyproject_sha256": sha256_file(pyproject),
        "uv_lock_sha256": sha256_file(uv_lock),
    }


def locked_versions() -> dict[str, str]:
    lock_path = SOURCE_WT / "uv.lock"
    with lock_path.open("rb") as f:
        lock = tomllib.load(f)

    versions: dict[str, set[str]] = {name: set() for name in CRITICAL_PACKAGES}
    for package in lock.get("package", []):
        name = package.get("name")
        version = package.get("version")
        if name in versions and isinstance(version, str):
            versions[name].add(version)

    resolved: dict[str, str] = {}
    for name, found in versions.items():
        if len(found) != 1:
            raise RuntimeError(
                f"SOURCE_LOCK_VERSION_AMBIGUOUS:{name}:{sorted(found)}"
            )
        resolved[name] = next(iter(found))

    if resolved["mlforecast"] != "1.1.0":
        raise RuntimeError(
            f"MLFORECAST_LOCK_VERSION_UNEXPECTED:{resolved['mlforecast']}"
        )
    if not resolved["optuna"].startswith("4."):
        raise RuntimeError(f"OPTUNA_LOCK_VERSION_UNEXPECTED:{resolved['optuna']}")

    return resolved


def write_runtime_project(versions: dict[str, str]) -> Path:
    PROJECT.mkdir(parents=True, exist_ok=True)
    pyproject = PROJECT / "pyproject.toml"
    dependencies = "\n".join(
        f'  "{name}=={versions[name]}",'
        for name in CRITICAL_PACKAGES
    )
    pyproject.write_text(
        "\n".join(
            [
                "[project]",
                'name = "loto-phase5a-mlforecast-runtime"',
                'version = "0.0.0"',
                'requires-python = ">=3.13,<3.14"',
                "dependencies = [",
                dependencies,
                "]",
                "",
                "[tool.uv]",
                "package = false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return pyproject


def uv_call(args: list[str], *, env: dict[str, str] | None = None) -> None:
    p = run(args, cwd=PROJECT, env=env, timeout=1200)
    log_name = "-".join(arg.strip("-").replace("/", "_") for arg in args[1:3])
    (OUT / f"{log_name}.stdout.log").write_text(p.stdout, encoding="utf-8")
    (OUT / f"{log_name}.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(
            f"UV_COMMAND_FAILED:rc={p.returncode}:cmd={' '.join(args)}:stderr={p.stderr[-3000:]}"
        )


def materialize_runtime() -> dict[str, Any]:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("UV_NOT_FOUND")

    versions = locked_versions()
    runtime_pyproject = write_runtime_project(versions)

    uv_version_p = run([uv, "--version"], timeout=60)
    if uv_version_p.returncode != 0:
        raise RuntimeError(f"UV_VERSION_FAILED:{uv_version_p.stderr.strip()}")

    uv_call([uv, "lock", "--project", str(PROJECT), "--python", "3.13"])
    runtime_lock = PROJECT / "uv.lock"
    if not runtime_lock.is_file():
        raise RuntimeError("BOOTSTRAP_UV_LOCK_MISSING")

    # This path is dedicated to Phase 5A and may be recreated deterministically.
    if RUNTIME.exists():
        if RUNTIME != ROOT / ".runtime-envs" / "phase5a-mlforecast-py313":
            raise RuntimeError("RUNTIME_DELETE_SAFETY_GATE_FAILED")
        shutil.rmtree(RUNTIME)
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)

    sync_env = os.environ.copy()
    sync_env.update(
        {
            "UV_PROJECT_ENVIRONMENT": str(RUNTIME),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    uv_call(
        [
            uv,
            "sync",
            "--project",
            str(PROJECT),
            "--python",
            "3.13",
            "--frozen",
            "--no-dev",
        ],
        env=sync_env,
    )

    python = RUNTIME / "bin" / "python"
    if not python.is_file():
        raise RuntimeError(f"BOOTSTRAP_RUNTIME_PYTHON_MISSING:{python}")

    return {
        "uv": uv,
        "uv_version": uv_version_p.stdout.strip(),
        "critical_versions_from_source_lock": versions,
        "runtime_project_pyproject": str(runtime_pyproject),
        "runtime_project_pyproject_sha256": sha256_file(runtime_pyproject),
        "runtime_project_uv_lock": str(runtime_lock),
        "runtime_project_uv_lock_sha256": sha256_file(runtime_lock),
    }


def verify_runtime(expected: dict[str, str]) -> dict[str, Any]:
    python = RUNTIME / "bin" / "python"
    code = r'''
import importlib
import importlib.metadata as md
import json
import platform
import sys

from mlforecast.auto import (
    AutoCatboost,
    AutoElasticNet,
    AutoLasso,
    AutoLightGBM,
    AutoLinearRegression,
    AutoMLForecast,
    AutoRandomForest,
    AutoRidge,
    AutoXGBoost,
)
from loto.parameter_effectiveness.adapters import MLForecastParameterAdapter

packages = ["mlforecast", "optuna", "numpy", "pandas", "pydantic", "scikit-learn"]
versions = {name: md.version(name) for name in packages}
classes = [
    AutoCatboost,
    AutoElasticNet,
    AutoLasso,
    AutoLightGBM,
    AutoLinearRegression,
    AutoMLForecast,
    AutoRandomForest,
    AutoRidge,
    AutoXGBoost,
]
print(json.dumps({
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "versions": versions,
    "mlforecast_auto_classes_imported": [cls.__name__ for cls in classes],
    "platform_adapter_imported": MLForecastParameterAdapter.__name__,
}, sort_keys=True))
'''
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SOURCE_WT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    p = run([str(python), "-c", code], cwd=SOURCE_WT, env=env, timeout=180)
    (OUT / "runtime-probe.stdout.log").write_text(p.stdout, encoding="utf-8")
    (OUT / "runtime-probe.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"RUNTIME_PROBE_FAILED:rc={p.returncode}:{p.stderr[-3000:]}")

    result = json.loads(p.stdout)
    if not str(result.get("python", "")).startswith("3.13."):
        raise RuntimeError(f"RUNTIME_PYTHON_VERSION_FAILED:{result.get('python')}")
    for name, version in expected.items():
        actual = (result.get("versions") or {}).get(name)
        if actual != version:
            raise RuntimeError(
                f"RUNTIME_PACKAGE_VERSION_FAILED:{name}:expected={version}:actual={actual}"
            )
    if result.get("platform_adapter_imported") != "MLForecastParameterAdapter":
        raise RuntimeError("PLATFORM_ADAPTER_IMPORT_FAILED")
    if "AutoLinearRegression" not in result.get("mlforecast_auto_classes_imported", []):
        raise RuntimeError("AUTO_LINEAR_REGRESSION_IMPORT_FAILED")
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    before: dict[str, Any] | None = None
    try:
        before = source_gate()
        materialized = materialize_runtime()
        expected = materialized["critical_versions_from_source_lock"]
        probe = verify_runtime(expected)
        after = source_gate()

        source_unchanged = (
            before["source_sha"] == after["source_sha"]
            and before["pyproject_sha256"] == after["pyproject_sha256"]
            and before["uv_lock_sha256"] == after["uv_lock_sha256"]
        )
        if not source_unchanged:
            raise RuntimeError("SOURCE_DEPENDENCY_CONTRACT_DRIFT")

        summary = {
            "schema_version": 1,
            "phase": "PHASE5A_MLFORECAST_RUNTIME_BOOTSTRAP",
            "status": "VERIFIED",
            "source_sha": EXPECTED_SOURCE_SHA,
            "runtime": str(RUNTIME),
            "runtime_python": str(RUNTIME / "bin" / "python"),
            "runtime_created": True,
            "source_dependencies_modified": False,
            "source_lockfile_modified": False,
            "source_contract_before": before,
            "source_contract_after": after,
            "materialization": materialized,
            "probe": probe,
            "next": "rerun_phase5a_parameter_effectiveness_runner_v2",
        }
        dump_json(SUMMARY, summary)
        print("=" * 72)
        print("PHASE5A_MLFORECAST_RUNTIME_BOOTSTRAP=VERIFIED")
        print(f"RUNTIME={RUNTIME}")
        print(f"PYTHON={probe['python']}")
        print(f"MLFORECAST={probe['versions']['mlforecast']}")
        print(f"OPTUNA={probe['versions']['optuna']}")
        print(f"SUMMARY={SUMMARY}")
        print("SOURCE_DEPENDENCIES_MODIFIED=False")
        print("SOURCE_LOCKFILE_MODIFIED=False")
        print("NEXT=RERUN_PHASE5A_V2")
        print("=" * 72)
        return 0
    except Exception as exc:
        failed = {
            "schema_version": 1,
            "phase": "PHASE5A_MLFORECAST_RUNTIME_BOOTSTRAP",
            "status": "FAILED",
            "source_sha": EXPECTED_SOURCE_SHA,
            "runtime": str(RUNTIME),
            "source_contract_before": before,
            "error": f"{type(exc).__name__}:{exc}",
        }
        dump_json(SUMMARY, failed)
        print("=" * 72)
        print("PHASE5A_MLFORECAST_RUNTIME_BOOTSTRAP=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print(f"SUMMARY={SUMMARY}")
        print("PHASE5A_PUBLISH=NOT_APPLICABLE")
        print("=" * 72)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
