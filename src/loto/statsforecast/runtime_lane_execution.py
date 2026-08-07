from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .runtime_lane_artifacts import (
    TARGET_PACKAGE,
    TARGET_VERSION,
    run_command,
    utc_now,
    venv_python,
    verify_portable_sha256sums,
    write_json,
)
from .runtime_lane_wheel_policy import verify_offline_bundle


def execute_runtime_lane(
    repo_root: Path,
    output_root: Path,
    *,
    run_id: str,
    wheelhouse: Path | None = None,
    offline: bool = False,
    uv_executable: str = "uv",
    horizon: int = 1,
    seed: int = 1,
) -> Path:
    if offline and wheelhouse is None:
        raise ValueError("offline execution requires a wheelhouse")
    bundle_verification = None
    if offline and wheelhouse is not None:
        bundle_verification = verify_offline_bundle(wheelhouse)
        if bundle_verification["status"] != "PASS":
            failures = bundle_verification["failures"]
            raise ValueError(
                f"offline bundle failed verification: {failures}"
            )
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    environment_dir = run_dir / "environment"
    environment_dir.mkdir()
    if offline and wheelhouse is not None:
        shutil.copy2(
            wheelhouse / "project" / "pyproject.toml",
            environment_dir,
        )
        shutil.copy2(
            wheelhouse / "project" / "uv.lock",
            environment_dir,
        )
    else:
        template = (
            repo_root
            / "environments"
            / "statsforecast-py313"
            / "pyproject.toml"
        )
        shutil.copy2(template, environment_dir / "pyproject.toml")
    commands: list[dict[str, Any]] = []
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(environment_dir / ".venv")
    if wheelhouse is not None:
        packages = wheelhouse / "packages"
        find_links = (
            packages.resolve()
            if packages.is_dir()
            else wheelhouse.resolve()
        )
        env["UV_FIND_LINKS"] = str(find_links)
    if offline:
        env["UV_OFFLINE"] = "1"
        env["UV_NO_INDEX"] = "1"
    lock_rc = 0
    if not offline:
        lock_command = [
            uv_executable,
            "lock",
            "--project",
            str(environment_dir),
            "--python",
            "3.13",
        ]
        lock_rc = run_command(
            lock_command,
            cwd=repo_root,
            env=env,
            stdout_path=run_dir / "uv-lock.stdout.log",
            stderr_path=run_dir / "uv-lock.stderr.log",
        )
        commands.append(
            {
                "phase": "lock",
                "command": lock_command,
                "returncode": lock_rc,
            }
        )
    sync_rc = -1
    certification_rc = -1
    checksum_report: dict[str, Any] = {
        "status": "NOT_RUN",
        "failures": [],
        "verified": 0,
    }
    inner_run: Path | None = None
    if lock_rc == 0:
        sync_command = [
            uv_executable,
            "sync",
            "--project",
            str(environment_dir),
            "--locked",
            "--no-install-project",
        ]
        sync_rc = run_command(
            sync_command,
            cwd=repo_root,
            env=env,
            stdout_path=run_dir / "uv-sync.stdout.log",
            stderr_path=run_dir / "uv-sync.stderr.log",
        )
        commands.append(
            {
                "phase": "sync",
                "command": sync_command,
                "returncode": sync_rc,
            }
        )
    if sync_rc == 0:
        python = venv_python(environment_dir / ".venv")
        certification_output = run_dir / "certification"
        parameters = (
            repo_root
            / "configs"
            / "statsforecast"
            / "runtime_parameters.json"
        )
        certification_command = [
            str(python),
            "-m",
            "loto.statsforecast.certify",
            "--output-root",
            str(certification_output),
            "--model-parameters",
            str(parameters),
            "--horizon",
            str(horizon),
            "--seed",
            str(seed),
        ]
        cert_env = env.copy()
        cert_env["PYTHONPATH"] = str(repo_root / "src")
        certification_rc = run_command(
            certification_command,
            cwd=repo_root,
            env=cert_env,
            stdout_path=run_dir / "certification.stdout.log",
            stderr_path=run_dir / "certification.stderr.log",
        )
        commands.append(
            {
                "phase": "certification",
                "command": certification_command,
                "returncode": certification_rc,
            }
        )
        stdout = (run_dir / "certification.stdout.log").read_text(
            encoding="utf-8"
        )
        for line in stdout.splitlines():
            if line.startswith("RUN_DIR="):
                inner_run = Path(
                    line.removeprefix("RUN_DIR=").strip()
                )
                break
        if inner_run is not None:
            checksum_report = verify_portable_sha256sums(inner_run)
    status = (
        "PASS"
        if certification_rc == 0
        and checksum_report["status"] == "PASS"
        else "PARTIAL"
    )
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "target_package": TARGET_PACKAGE,
        "target_version": TARGET_VERSION,
        "python_lane": "3.13",
        "offline": offline,
        "wheelhouse": (
            str(wheelhouse.resolve())
            if wheelhouse is not None
            else None
        ),
        "offline_bundle_verification": bundle_verification,
        "lock_returncode": lock_rc,
        "sync_returncode": sync_rc,
        "certification_returncode": certification_rc,
        "inner_run": (
            str(inner_run) if inner_run is not None else None
        ),
        "inner_checksum_verification": checksum_report,
        "holdout_opened": False,
        "prospective_actual_known": False,
        "finished_at_utc": utc_now(),
    }
    write_json(run_dir / "COMMANDS.json", commands)
    write_json(run_dir / "RUNTIME_LANE_REPORT.json", report)
    return run_dir


__all__ = ["execute_runtime_lane"]
