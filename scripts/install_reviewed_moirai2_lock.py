from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.lock_review import (  # noqa: E402
    APPROVAL_FILENAME,
    LOCK_FILENAME,
    REPORT_FILENAME,
    build_approval,
    inspect_lock,
    load_json_object,
    sha256_file,
    sha256_payload,
    validate_installed_review,
    write_sha256_manifest,
)


RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}
APPROVAL_TOKEN = "APPLY-REVIEWED-MOIRAI2-LOCK"


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def install_candidate(
    *,
    candidate_dir: Path,
    output_dir: Path,
    runtime_lane: str,
    reviewer: str,
    reviewed_at: str,
    expected_lock_sha256: str,
    approval_token: str,
    apply: bool,
    replace_existing_sha256: str | None,
) -> dict[str, Any]:
    if runtime_lane not in RUNTIME_LANES:
        raise ValueError(f"unsupported runtime lane: {runtime_lane}")
    if approval_token != APPROVAL_TOKEN:
        raise PermissionError("approval token does not match")
    if not output_dir.is_dir():
        raise FileNotFoundError("installation output directory was not initialized")
    candidate_pyproject = candidate_dir / "candidate-project" / "pyproject.toml"
    candidate_lock = candidate_dir / "candidate-project" / LOCK_FILENAME
    candidate_report_path = candidate_dir / REPORT_FILENAME
    required = (candidate_pyproject, candidate_lock, candidate_report_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"candidate artifacts are missing: {missing}")
    if sha256_file(candidate_lock) != expected_lock_sha256:
        raise ValueError("expected candidate lock SHA-256 does not match")

    report = load_json_object(candidate_report_path)
    recomputed = inspect_lock(
        pyproject_path=candidate_pyproject,
        lock_path=candidate_lock,
        runtime_lane=runtime_lane,
    )
    if sha256_payload(report) != sha256_payload(recomputed):
        raise ValueError("candidate review report does not match candidate artifacts")

    environment = RUNTIME_LANES[runtime_lane]
    lane_pyproject = environment / "pyproject.toml"
    if not lane_pyproject.is_file():
        raise FileNotFoundError(f"lane pyproject is missing: {lane_pyproject}")
    if sha256_file(lane_pyproject) != report["pyproject_sha256"]:
        raise ValueError("lane pyproject changed after candidate generation")

    approval = build_approval(
        report=report,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )
    targets = {
        LOCK_FILENAME: environment / LOCK_FILENAME,
        REPORT_FILENAME: environment / REPORT_FILENAME,
        APPROVAL_FILENAME: environment / APPROVAL_FILENAME,
    }
    existing = [path for path in targets.values() if path.exists()]
    if existing:
        current_lock = targets[LOCK_FILENAME]
        if not current_lock.is_file() or replace_existing_sha256 is None:
            raise FileExistsError(
                "existing reviewed-lock artifacts require --replace-existing-sha256"
            )
        if sha256_file(current_lock) != replace_existing_sha256:
            raise ValueError("existing lock SHA-256 does not match replacement guard")

    plan = {
        "schema_version": "moirai2-lock-installation-v1",
        "status": "READY",
        "runtime_lane": runtime_lane,
        "candidate_dir": str(candidate_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "environment": str(environment.resolve()),
        "candidate_lock_sha256": expected_lock_sha256,
        "candidate_report_sha256": sha256_payload(report),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "apply_requested": apply,
        "replace_existing": bool(existing),
        "target_files": {name: str(path.resolve()) for name, path in targets.items()},
    }
    if not apply:
        return plan

    backup_dir: Path | None = None
    if existing:
        backup_dir = output_dir / "backup-before-install"
        backup_dir.mkdir(parents=False, exist_ok=False)
        for path in existing:
            shutil.copy2(path, backup_dir / path.name)

    _atomic_copy(candidate_lock, targets[LOCK_FILENAME])
    _atomic_copy(candidate_report_path, targets[REPORT_FILENAME])
    _write_json(targets[APPROVAL_FILENAME], approval)
    evidence = validate_installed_review(
        environment_path=environment,
        runtime_lane=runtime_lane,
    )
    return {
        **plan,
        "status": "INSTALLED",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "backup_dir": str(backup_dir.resolve()) if backup_dir else None,
        "installed_review": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install a human-approved Moirai 2.0 lock candidate"
    )
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--runtime-lane", required=True, choices=sorted(RUNTIME_LANES))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--replace-existing-sha256")
    arguments = parser.parse_args()
    if arguments.output_dir.exists():
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "message": "output directory already exists",
                    "output_dir": str(arguments.output_dir),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        result = install_candidate(
            candidate_dir=arguments.candidate_dir,
            output_dir=arguments.output_dir,
            runtime_lane=arguments.runtime_lane,
            reviewer=arguments.reviewer,
            reviewed_at=arguments.reviewed_at,
            expected_lock_sha256=arguments.expected_lock_sha256,
            approval_token=arguments.approval_token,
            apply=arguments.apply,
            replace_existing_sha256=arguments.replace_existing_sha256,
        )
    except Exception as exc:
        result = {
            "schema_version": "moirai2-lock-installation-v1",
            "status": "FAILED",
            "runtime_lane": arguments.runtime_lane,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        _write_json(arguments.output_dir / "INSTALLATION_EVIDENCE.json", result)
        write_sha256_manifest(
            arguments.output_dir,
            arguments.output_dir / "SHA256SUMS",
        )
        return 2
    _write_json(arguments.output_dir / "INSTALLATION_EVIDENCE.json", result)
    write_sha256_manifest(
        arguments.output_dir,
        arguments.output_dir / "SHA256SUMS",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
