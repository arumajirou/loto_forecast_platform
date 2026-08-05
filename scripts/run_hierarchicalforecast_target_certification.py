#!/usr/bin/env python3
"""Provision, run, and independently verify formal HierarchicalForecast certification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

TARGET_VERSION = "1.5.1"
GAMES = ("mini", "loto6", "loto7", "bingo5")
EXECUTABLE = (
    "BottomUp",
    "BottomUpSparse",
    "MinTrace",
    "MinTraceSparse",
    "OptimalCombination",
    "ERM",
)
UNSUPPORTED = ("TopDown", "TopDownSparse", "MiddleOut", "MiddleOutSparse")
METHODS = (*EXECUTABLE, *UNSUPPORTED)
EXPECTED_STATUS = {
    **{method: "VERIFIED" for method in EXECUTABLE},
    **{method: "UNSUPPORTED_HIERARCHY" for method in UNSUPPORTED},
}
PRIMARY = (
    "RUNTIME_CERTIFICATION.json",
    "METHOD_RESULTS.json",
    "INPUT_EVIDENCE.json",
    "ARTIFACT_MANIFEST.json",
)
REQUIRED = (*PRIMARY, "SHA256SUMS")
PACKAGE_MANIFEST = "PACKAGE_MANIFEST.json"


class CertificationError(RuntimeError):
    """Raised when target-machine evidence cannot be accepted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"JSON root must be an object: {path}")
    return payload


def run_command(
    command: Sequence[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, object]:
    started_at = utc_now()
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    atomic_write(stdout_path, completed.stdout.encode())
    atomic_write(stderr_path, completed.stderr.encode())
    return {
        "command": list(command),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": time.perf_counter() - started,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def git_state(root: Path) -> dict[str, object]:
    def capture(args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise CertificationError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    status = capture(["status", "--porcelain=v1", "--untracked-files=all"])
    return {
        "commit": capture(["rev-parse", "HEAD"]),
        "branch": capture(["rev-parse", "--abbrev-ref", "HEAD"]),
        "clean": not bool(status),
        "status_porcelain": status.splitlines() if status else [],
    }


def safe_name(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
        raise CertificationError(f"unsafe artifact path: {value!r}")
    if not value or path.name != value:
        raise CertificationError(f"invalid artifact name: {value!r}")
    return value


def checksums(path: Path, expected: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        if not row.strip():
            continue
        try:
            digest, name = row.split("  ", 1)
        except ValueError as exc:
            raise CertificationError(f"invalid checksum row: {row!r}") from exc
        name = safe_name(name)
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CertificationError(f"invalid SHA-256: {name}")
        if name in result:
            raise CertificationError(f"duplicate checksum entry: {name}")
        result[name] = digest
    if set(result) != expected:
        raise CertificationError("checksum coverage mismatch")
    return result


def inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise CertificationError(f"{label} escapes expected root: {resolved}") from exc
    return resolved


def verify_runtime_files(run_dir: Path, run_id: str) -> None:
    for name in REQUIRED:
        if not (run_dir / name).is_file():
            raise CertificationError(f"missing runtime artifact: {name}")
    for name, digest in checksums(run_dir / "SHA256SUMS", set(PRIMARY)).items():
        if sha_file(run_dir / name) != digest:
            raise CertificationError(f"runtime checksum mismatch: {name}")
    manifest = load_json(run_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("run_id") != run_id or not isinstance(manifest.get("files"), list):
        raise CertificationError("invalid runtime artifact manifest")
    observed: set[str] = set()
    for row in manifest["files"]:
        if not isinstance(row, dict):
            raise CertificationError("invalid artifact manifest row")
        name = safe_name(str(row.get("path", "")))
        observed.add(name)
        path = run_dir / name
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha_file(path):
            raise CertificationError(f"artifact manifest mismatch: {name}")
    if observed != set(PRIMARY[:3]):
        raise CertificationError("artifact manifest coverage mismatch")


def verify_cases(run_dir: Path, run_id: str) -> dict[str, int]:
    payload = load_json(run_dir / "METHOD_RESULTS.json")
    rows = payload.get("results")
    if payload.get("run_id") != run_id or not isinstance(rows, list) or len(rows) != 40:
        raise CertificationError("method results must contain exactly 40 rows")
    observed: set[tuple[str, str]] = set()
    executed = 0
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            raise CertificationError("method result row must be an object")
        key = (str(row.get("game", "")), str(row.get("method", "")))
        game, method = key
        if game not in GAMES or method not in METHODS or key in observed:
            raise CertificationError(f"invalid or duplicate formal case: {key}")
        observed.add(key)
        expected = EXPECTED_STATUS[method]
        checks = row.get("checks")
        result = row.get("result")
        if row.get("expected_status") != expected or row.get("case_status") != "PASS":
            raise CertificationError(f"formal case state mismatch: {key}")
        if (
            not isinstance(checks, dict)
            or not checks
            or not all(value is True for value in checks.values())
        ):
            raise CertificationError(f"formal checks failed: {key}")
        if not isinstance(result, dict) or result.get("status") != expected:
            raise CertificationError(f"observed status mismatch: {key}")
        actual = result.get("actual_execution")
        if method in EXECUTABLE:
            if actual is not True:
                raise CertificationError(f"execution evidence missing: {key}")
            executed += 1
        else:
            if actual is not False:
                raise CertificationError(f"unsupported method executed: {key}")
            rejected += 1
    expected_pairs = {(game, method) for game in GAMES for method in METHODS}
    if observed != expected_pairs or executed != 24 or rejected != 16:
        raise CertificationError("formal method/game partition mismatch")
    inputs = load_json(run_dir / "INPUT_EVIDENCE.json")
    if inputs.get("run_id") != run_id or set(inputs.get("games", {})) != set(GAMES):
        raise CertificationError("input evidence game coverage mismatch")
    return {"executed_cases": executed, "rejected_cases": rejected}


def verify_zip(zip_path: Path, run_id: str) -> dict[str, object]:
    expected = {*(f"{run_id}/{name}" for name in REQUIRED), f"{run_id}/{PACKAGE_MANIFEST}"}
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != expected:
                raise CertificationError("ZIP coverage or duplicate-member failure")
            for info in infos:
                member = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    member.is_absolute()
                    or ".." in member.parts
                    or len(member.parts) != 2
                    or member.parts[0] != run_id
                    or info.is_dir()
                    or info.flag_bits & 1
                    or info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.create_system != 3
                    or mode != 0o100644
                ):
                    raise CertificationError(f"invalid ZIP member: {info.filename}")
            if archive.testzip() is not None:
                raise CertificationError("ZIP CRC verification failed")
            manifest_bytes = archive.read(f"{run_id}/{PACKAGE_MANIFEST}")
            manifest = json.loads(manifest_bytes.decode())
            if not isinstance(manifest, dict) or manifest_bytes != canonical(manifest):
                raise CertificationError("package manifest is not canonical")
            if (
                manifest.get("run_id") != run_id
                or manifest.get("certification_status") != "VERIFIED"
            ):
                raise CertificationError("package manifest identity/status mismatch")
            rows = manifest.get("files")
            if not isinstance(rows, list):
                raise CertificationError("package manifest files must be a list")
            observed: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise CertificationError("invalid package manifest row")
                name = safe_name(str(row.get("path", "")))
                if name in observed:
                    raise CertificationError(f"duplicate package manifest row: {name}")
                observed.add(name)
                data = archive.read(f"{run_id}/{name}")
                digest = hashlib.sha256(data).hexdigest()
                if row.get("bytes") != len(data) or row.get("sha256") != digest:
                    raise CertificationError(f"ZIP member evidence mismatch: {name}")
            if observed != set(REQUIRED):
                raise CertificationError("package manifest coverage mismatch")
            content_set = hashlib.sha256(canonical(rows)).hexdigest()
            if manifest.get("content_set_sha256") != content_set:
                raise CertificationError("package content-set hash mismatch")
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise CertificationError(f"ZIP verification failed: {exc}") from exc
    return {
        "sha256": sha_file(zip_path),
        "bytes": zip_path.stat().st_size,
        "member_count": len(expected),
        "content_set_sha256": manifest["content_set_sha256"],
    }


def verify_formal(payload: dict[str, Any], output_root: Path, git_sha: str) -> dict[str, object]:
    certification = payload.get("certification")
    package = payload.get("package")
    if not isinstance(certification, dict) or not isinstance(package, dict):
        raise CertificationError("CLI output lacks certification/package objects")
    summary = certification.get("summary")
    expected_summary = {
        "expected_cases": 40,
        "executed_cases": 40,
        "passed_cases": 40,
        "failed_cases": 0,
        "exact_version_match": True,
        "module_distribution_version_consistent": True,
    }
    if (
        certification.get("status") != "VERIFIED"
        or certification.get("formal_success") is not True
        or not isinstance(summary, dict)
        or any(summary.get(key) != value for key, value in expected_summary.items())
    ):
        raise CertificationError("formal status or 40-case summary mismatch")
    dependency = certification.get("dependency")
    runtime = certification.get("runtime")
    if not isinstance(dependency, dict) or dependency.get("installed_version") != TARGET_VERSION:
        raise CertificationError("runtime installed-version evidence mismatch")
    if not isinstance(runtime, dict) or runtime.get("git_commit") != git_sha:
        raise CertificationError("runtime git-commit evidence mismatch")
    run_id = str(certification.get("run_id", ""))
    run_dir = inside(
        Path(str(certification.get("run_directory", ""))),
        output_root,
        "run directory",
    )
    if not run_id or run_dir.name != run_id or not run_dir.is_dir():
        raise CertificationError("run directory and run_id mismatch")
    verify_runtime_files(run_dir, run_id)
    if load_json(run_dir / "RUNTIME_CERTIFICATION.json") != certification:
        raise CertificationError("persisted certification differs from CLI output")
    partition = verify_cases(run_dir, run_id)
    zip_path = inside(Path(str(package.get("path", ""))), output_root, "ZIP")
    sidecar = inside(Path(str(package.get("sha256_sidecar", ""))), output_root, "sidecar")
    if zip_path != run_dir.with_suffix(".zip") or sidecar != Path(f"{zip_path}.sha256"):
        raise CertificationError("package path relationship mismatch")
    digest = sha_file(zip_path)
    if sidecar.read_text(encoding="utf-8") != f"{digest}  {zip_path.name}\n":
        raise CertificationError("ZIP sidecar mismatch")
    zip_result = verify_zip(zip_path, run_id)
    expected_package = {
        "status": "VERIFIED",
        "run_id": run_id,
        "certification_status": "VERIFIED",
        "sha256": digest,
        "bytes": zip_result["bytes"],
        "member_count": zip_result["member_count"],
        "content_set_sha256": zip_result["content_set_sha256"],
    }
    if any(package.get(key) != value for key, value in expected_package.items()):
        raise CertificationError("CLI package evidence mismatch")
    return {
        "run_id": run_id,
        "run_directory": str(run_dir),
        "summary": summary,
        "method_partition": partition,
        "zip_path": str(zip_path),
        "zip_sha256": digest,
        "zip_sidecar": str(sidecar),
        "zip_member_count": zip_result["member_count"],
        "zip_bytes": zip_result["bytes"],
    }


def finalize(directory: Path, commands: list[dict[str, object]], report: dict[str, object]) -> None:
    atomic_write(directory / "COMMANDS.json", canonical({"commands": commands}))
    atomic_write(directory / "OPERATOR_REPORT.json", canonical(report))
    files = sorted(
        [path for path in directory.iterdir() if path.is_file()],
        key=lambda path: path.name,
    )
    manifest = {
        "operator_run_id": report["operator_run_id"],
        "files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path)}
            for path in files
        ],
    }
    manifest_path = directory / "ARTIFACT_MANIFEST.json"
    atomic_write(manifest_path, canonical(manifest))
    atomic_write(
        directory / "SHA256SUMS",
        "".join(f"{sha_file(path)}  {path.name}\n" for path in [*files, manifest_path]).encode(),
    )


def execute(
    root: Path,
    output_root: Path,
    operator_root: Path,
    expected_git_sha: str | None = None,
    skip_sync: bool = False,
    runner: Callable[[Sequence[str], Path, Path, Path], dict[str, object]] = run_command,
    probe: Callable[[Path], dict[str, object]] = git_state,
) -> tuple[dict[str, object], int]:
    root = root.resolve()
    output_root = (
        (root / output_root).resolve()
        if not output_root.is_absolute()
        else output_root.resolve()
    )
    operator_root = (
        (root / operator_root).resolve()
        if not operator_root.is_absolute()
        else operator_root.resolve()
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"hierarchicalforecast-target-{stamp}-{os.getpid()}"
    directory = operator_root / run_id
    report: dict[str, object] = {
        "operator_run_id": run_id,
        "status": "FAILED_PREFLIGHT",
        "phase": "preflight",
        "formal_success": False,
        "started_at": utc_now(),
        "finished_at": None,
        "repo_root": str(root),
        "output_root": str(output_root),
        "operator_directory": str(directory),
        "expected_version": TARGET_VERSION,
        "git": None,
        "certification": None,
        "error": None,
    }
    commands: list[dict[str, object]] = []
    exit_code = 3
    try:
        state = probe(root)
        report["git"] = state
        if state.get("clean") is not True:
            raise CertificationError("formal certification requires a clean worktree")
        git_sha = str(state.get("commit", ""))
        if not git_sha or expected_git_sha and git_sha != expected_git_sha:
            raise CertificationError("git commit does not match the expected head")
        directory.mkdir(parents=True, exist_ok=False)
        output_root.mkdir(parents=True, exist_ok=True)

        def command(name: str, args: list[str]) -> dict[str, object]:
            result = runner(
                args,
                root,
                directory / f"{name}.stdout.log",
                directory / f"{name}.stderr.log",
            )
            commands.append(result)
            return result

        if not skip_sync:
            report["phase"] = "sync"
            if command("sync", ["uv", "sync", "--extra", "full", "--locked"])["returncode"]:
                report["status"] = "FAILED_SYNC"
                raise CertificationError("uv sync failed")
        report["phase"] = "dependency"
        version = command(
            "version",
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-c",
                "from importlib.metadata import version; print(version('hierarchicalforecast'))",
            ],
        )
        installed = Path(str(version["stdout_path"])).read_text(encoding="utf-8").strip()
        report["installed_version"] = installed
        if version["returncode"] or installed != TARGET_VERSION:
            report["status"] = "FAILED_VERSION_MISMATCH"
            exit_code = 2
            raise CertificationError(f"installed version is {installed!r}")
        report["phase"] = "certification"
        certification = command(
            "certification",
            [
                "uv",
                "run",
                "--locked",
                "loto-hierarchicalforecast-certify",
                "--output-root",
                str(output_root),
                "--expected-version",
                TARGET_VERSION,
            ],
        )
        try:
            payload = json.loads(
                Path(str(certification["stdout_path"])).read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise CertificationError(f"certification output is not JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise CertificationError("certification output root is not an object")
        if certification["returncode"]:
            nested = payload.get("certification")
            report["status"] = str(
                nested.get("status") if isinstance(nested, dict) else payload.get("status")
            )
            report["certification"] = payload
            exit_code = 2 if certification["returncode"] == 2 else 3
            raise CertificationError("formal certification command failed")
        report["phase"] = "verification"
        report["certification"] = verify_formal(payload, output_root, git_sha)
        report["status"] = "VERIFIED"
        report["phase"] = "complete"
        report["formal_success"] = True
        report["checks"] = {
            "clean_git": True,
            "exact_version": True,
            "exit_zero": True,
            "forty_cases": True,
            "twenty_four_executed": True,
            "sixteen_rejected": True,
            "runtime_hashes": True,
            "zip_and_sidecar": True,
        }
        exit_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if report["status"] == "FAILED_PREFLIGHT":
            report["status"] = {
                "preflight": "FAILED_PREFLIGHT",
                "sync": "FAILED_SYNC",
                "dependency": "FAILED_VERSION_PROBE",
                "certification": "FAILED_CERTIFICATION_OUTPUT",
                "verification": "FAILED_OPERATOR_VERIFICATION",
            }.get(str(report["phase"]), "FAILED_OPERATOR")
    finally:
        report["finished_at"] = utc_now()
        directory.mkdir(parents=True, exist_ok=True)
        finalize(directory, commands, report)
    return report, exit_code


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-runtime"),
    )
    result.add_argument(
        "--operator-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-target-runs"),
    )
    result.add_argument("--expected-git-sha")
    result.add_argument("--skip-sync", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report, exit_code = execute(
        args.repo_root,
        args.output_root,
        args.operator_root,
        expected_git_sha=args.expected_git_sha,
        skip_sync=args.skip_sync,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
