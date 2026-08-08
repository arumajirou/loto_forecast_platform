from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.lock_review import (  # noqa: E402
    REPORT_FILENAME,
    inspect_lock,
    sha256_file,
    write_sha256_manifest,
)

RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_inventory_csv(path: Path, packages: list[dict[str, Any]]) -> None:
    fieldnames = [
        "name",
        "version",
        "source_kind",
        "source_value",
        "is_root_project",
        "dependency_count",
        "artifact_hash_count",
        "dependency_names",
        "artifact_hashes",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for package in packages:
            writer.writerow(
                {
                    "name": package["name"],
                    "version": package["version"],
                    "source_kind": package["source_kind"],
                    "source_value": package["source_value"] or "",
                    "is_root_project": package["is_root_project"],
                    "dependency_count": len(package["dependency_names"]),
                    "artifact_hash_count": len(package["artifact_hashes"]),
                    "dependency_names": "|".join(package["dependency_names"]),
                    "artifact_hashes": "|".join(package["artifact_hashes"]),
                }
            )


def build_candidate(
    *,
    runtime_lane: str,
    output_dir: Path,
    python_spec: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    if runtime_lane not in RUNTIME_LANES:
        raise ValueError(f"unsupported runtime lane: {runtime_lane}")
    source_environment = RUNTIME_LANES[runtime_lane]
    source_pyproject = source_environment / "pyproject.toml"
    if not source_pyproject.is_file():
        raise FileNotFoundError(f"lane pyproject is missing: {source_pyproject}")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable is not available")

    output_dir.mkdir(parents=True, exist_ok=False)
    candidate_project = output_dir / "candidate-project"
    candidate_project.mkdir()
    candidate_pyproject = candidate_project / "pyproject.toml"
    shutil.copy2(source_pyproject, candidate_pyproject)

    command = [uv, "lock", "--project", str(candidate_project)]
    if python_spec:
        command.extend(["--python", python_spec])
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    (output_dir / "stdout.log").write_text(process.stdout, encoding="utf-8")
    (output_dir / "stderr.log").write_text(process.stderr, encoding="utf-8")
    (output_dir / "exit_code.txt").write_text(
        f"{process.returncode}\n",
        encoding="utf-8",
    )
    candidate_lock = candidate_project / "uv.lock"
    if process.returncode != 0 or not candidate_lock.is_file():
        result = {
            "schema_version": "moirai2-lock-candidate-v1",
            "status": "FAILED",
            "runtime_lane": runtime_lane,
            "generated_at": datetime.now(UTC).isoformat(),
            "command": command,
            "exit_code": process.returncode,
            "message": "uv lock did not produce a candidate lockfile",
        }
        _write_json(output_dir / "CANDIDATE_RESULT.json", result)
        _write_json(
            output_dir / "ARTIFACT_MANIFEST.json",
            {
                "status": "FAILED",
                "files": sorted(
                    path.relative_to(output_dir).as_posix()
                    for path in output_dir.rglob("*")
                    if path.is_file()
                ),
            },
        )
        write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")
        return result

    report = inspect_lock(
        pyproject_path=candidate_pyproject,
        lock_path=candidate_lock,
        runtime_lane=runtime_lane,
    )
    _write_json(output_dir / REPORT_FILENAME, report)
    _write_inventory_csv(output_dir / "LOCK_DEPENDENCY_INVENTORY.csv", report["packages"])
    result = {
        "schema_version": "moirai2-lock-candidate-v1",
        "status": "PASS" if report["status"] == "PASS" else "FAILED",
        "runtime_lane": runtime_lane,
        "generated_at": datetime.now(UTC).isoformat(),
        "command": command,
        "exit_code": process.returncode,
        "source_pyproject": str(source_pyproject.resolve()),
        "source_pyproject_sha256": sha256_file(source_pyproject),
        "candidate_pyproject_sha256": sha256_file(candidate_pyproject),
        "candidate_lock_sha256": sha256_file(candidate_lock),
        "review_status": report["status"],
        "violation_count": len(report["violations"]),
        "warning_count": len(report["warnings"]),
        "package_count": report["package_count"],
        "dependency_edge_count": report["dependency_edge_count"],
        "lane_modified": False,
    }
    _write_json(output_dir / "CANDIDATE_RESULT.json", result)
    _write_json(
        output_dir / "ARTIFACT_MANIFEST.json",
        {
            "status": result["status"],
            "files": sorted(
                path.relative_to(output_dir).as_posix()
                for path in output_dir.rglob("*")
                if path.is_file()
            ),
        },
    )
    write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-destructive Moirai 2.0 uv.lock candidate"
    )
    parser.add_argument("--runtime-lane", required=True, choices=sorted(RUNTIME_LANES))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--python")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
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
    try:
        result = build_candidate(
            runtime_lane=arguments.runtime_lane,
            output_dir=arguments.output_dir,
            python_spec=arguments.python,
            timeout_seconds=arguments.timeout_seconds,
        )
    except Exception as exc:
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            arguments.output_dir / "CANDIDATE_RESULT.json",
            {
                "schema_version": "moirai2-lock-candidate-v1",
                "status": "FAILED",
                "runtime_lane": arguments.runtime_lane,
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )
        write_sha256_manifest(arguments.output_dir, arguments.output_dir / "SHA256SUMS")
        return 2
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
