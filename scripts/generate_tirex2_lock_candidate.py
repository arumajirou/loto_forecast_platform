# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from loto.tirex2_campaign.lock_review import (
    LOCK_FILENAME,
    REPORT_FILENAME,
    inspect_lock,
    sha256_file,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _manifest(root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            continue
        entries.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return entries


def generate_candidate(
    *,
    environment_path: Path,
    output_root: Path,
    runtime_lane: str,
    uv_executable: str,
) -> dict[str, object]:
    project_path = environment_path / "pyproject.toml"
    if not project_path.is_file():
        raise FileNotFoundError(project_path)
    run_id = datetime.now(UTC).strftime("tirex2-lock-%Y%m%dT%H%M%SZ")
    candidate_path = output_root / run_id
    candidate_path.mkdir(parents=True, exist_ok=False)
    shutil.copy2(project_path, candidate_path / "pyproject.toml")
    command = [uv_executable, "lock"]
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command,
            cwd=candidate_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        exit_code = 127
        stderr = str(exc)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or "lock resolution timed out"
    (candidate_path / "uv-lock.stdout.log").write_text(stdout, encoding="utf-8")
    (candidate_path / "uv-lock.stderr.log").write_text(stderr, encoding="utf-8")
    (candidate_path / "uv-lock.exit-code.txt").write_text(
        f"{exit_code}\n",
        encoding="utf-8",
    )
    status: dict[str, object] = {
        "schema_version": "tirex2-lock-candidate-v1",
        "run_id": run_id,
        "runtime_lane": runtime_lane,
        "command": command,
        "exit_code": exit_code,
        "environment_pyproject_sha256": sha256_file(project_path),
        "candidate_path": str(candidate_path),
    }
    lock_path = candidate_path / LOCK_FILENAME
    if exit_code == 0 and lock_path.is_file():
        report = inspect_lock(
            pyproject_path=candidate_path / "pyproject.toml",
            lock_path=lock_path,
            runtime_lane=runtime_lane,
        )
        _write_json(candidate_path / REPORT_FILENAME, report)
        status["status"] = "PASS" if report["status"] == "PASS" else "FAILED_REVIEW"
        status["lock_sha256"] = report["lock_sha256"]
        status["review_status"] = report["status"]
    else:
        status["status"] = "FAILED_LOCK_RESOLUTION"
    _write_json(candidate_path / "CANDIDATE_STATUS.json", status)
    entries = _manifest(candidate_path)
    _write_json(candidate_path / "ARTIFACT_MANIFEST.json", entries)
    sums = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in entries)
    (candidate_path / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a non-destructive TiRex-2 lock candidate"
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=REPOSITORY_ROOT / "environments" / "tirex2-supported-py312",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--runtime-lane", default="tirex2-supported-py312")
    parser.add_argument("--uv-executable", default="uv")
    args = parser.parse_args()
    status = generate_candidate(
        environment_path=args.environment.resolve(strict=True),
        output_root=args.output_root.resolve(),
        runtime_lane=args.runtime_lane,
        uv_executable=args.uv_executable,
    )
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0 if status["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
