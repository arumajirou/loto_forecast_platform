from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from packaging.tags import Tag, sys_tags
from packaging.utils import parse_wheel_filename

TARGET_PACKAGE = "statsforecast"
TARGET_VERSION = "2.1.1"
PYPI_JSON_URL = f"https://pypi.org/pypi/{TARGET_PACKAGE}/{TARGET_VERSION}/json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json(payload) + b"\n")


def _release_files(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    version = str(payload.get("info", {}).get("version", ""))
    if version != TARGET_VERSION:
        raise ValueError(f"expected PyPI release {TARGET_VERSION}, got {version!r}")
    files = payload.get("urls")
    if not isinstance(files, list) or not files:
        raise ValueError("PyPI release contains no files")
    return [item for item in files if isinstance(item, Mapping)]


def select_compatible_release_file(
    payload: Mapping[str, Any],
    *,
    supported_tags: Iterable[Tag] | None = None,
) -> dict[str, Any]:
    files = _release_files(payload)
    ordered_tags = tuple(supported_tags or sys_tags())
    tag_rank = {tag: rank for rank, tag in enumerate(ordered_tags)}
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for item in files:
        if item.get("packagetype") != "bdist_wheel":
            continue
        filename = str(item.get("filename", ""))
        try:
            _, version, _, wheel_tags = parse_wheel_filename(filename)
        except ValueError:
            continue
        if str(version) != TARGET_VERSION:
            continue
        matching = [tag_rank[tag] for tag in wheel_tags if tag in tag_rank]
        if matching:
            candidates.append((min(matching), item))
    if candidates:
        selected = min(
            candidates,
            key=lambda value: (value[0], str(value[1]["filename"])),
        )[1]
    else:
        sdists = [item for item in files if item.get("packagetype") == "sdist"]
        if not sdists:
            raise ValueError("release has no compatible wheel or source distribution")
        selected = min(sdists, key=lambda item: str(item.get("filename", "")))
    digest = str(selected.get("digests", {}).get("sha256", ""))
    if len(digest) != 64:
        raise ValueError("selected PyPI artifact has no valid SHA-256")
    return {
        "filename": str(selected["filename"]),
        "url": str(selected["url"]),
        "packagetype": str(selected["packagetype"]),
        "sha256": digest,
        "size": int(selected.get("size", 0)),
        "requires_python": selected.get("requires_python"),
        "upload_time_iso_8601": selected.get("upload_time_iso_8601"),
    }


def fetch_release_artifact(
    wheelhouse: Path,
    *,
    metadata_url: str = PYPI_JSON_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    supported_tags: Iterable[Tag] | None = None,
) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    with opener(metadata_url, timeout=60) as response:
        metadata_bytes = response.read()
    metadata = json.loads(metadata_bytes)
    selected = select_compatible_release_file(metadata, supported_tags=supported_tags)
    with opener(selected["url"], timeout=180) as response:
        artifact_bytes = response.read()
    actual = _sha256_bytes(artifact_bytes)
    if actual != selected["sha256"]:
        raise ValueError(
            f"downloaded artifact SHA-256 mismatch: expected {selected['sha256']}, got {actual}"
        )
    artifact_path = wheelhouse / selected["filename"]
    _atomic_write(artifact_path, artifact_bytes)
    selection = {
        "schema_version": 1,
        "package": TARGET_PACKAGE,
        "version": TARGET_VERSION,
        "metadata_url": metadata_url,
        "selected": selected,
        "metadata_sha256": _sha256_bytes(metadata_bytes),
        "downloaded_sha256": actual,
        "downloaded_at_utc": _utc_now(),
    }
    _write_json(wheelhouse / "PYPI_RELEASE_SELECTION.json", selection)
    selection_path = wheelhouse / "PYPI_RELEASE_SELECTION.json"
    sums = [
        f"{actual}  {artifact_path.name}",
        f"{sha256_file(selection_path)}  PYPI_RELEASE_SELECTION.json",
    ]
    _atomic_write(
        wheelhouse / "SHA256SUMS",
        ("\n".join(sums) + "\n").encode("utf-8"),
    )
    return artifact_path


def verify_portable_sha256sums(
    root: Path,
    checksum_file: Path | None = None,
) -> dict[str, Any]:
    checksum_file = checksum_file or root / "SHA256SUMS"
    if not checksum_file.is_file():
        return {
            "status": "FAILED",
            "failures": ["SHA256SUMS is missing"],
            "verified": 0,
        }
    failures: list[str] = []
    verified = 0
    seen: set[str] = set()
    lines = checksum_file.read_text(encoding="utf-8").splitlines()
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            digest, relative = raw.split("  ", 1)
        except ValueError:
            failures.append(f"line {line_number}: malformed checksum row")
            continue
        posix = PurePosixPath(relative)
        valid_digest = len(digest) == 64 and all(
            character in "0123456789abcdef" for character in digest
        )
        if not valid_digest:
            failures.append(f"line {line_number}: invalid SHA-256")
            continue
        if posix.is_absolute() or ".." in posix.parts or not posix.parts:
            failures.append(f"line {line_number}: unsafe path {relative!r}")
            continue
        normalized = posix.as_posix()
        if normalized in seen:
            failures.append(f"line {line_number}: duplicate path {normalized!r}")
            continue
        seen.add(normalized)
        path = root.joinpath(*posix.parts)
        if not path.is_file() or path.is_symlink():
            failures.append(
                f"line {line_number}: missing or symlinked file {normalized!r}"
            )
            continue
        actual = sha256_file(path)
        if actual != digest:
            failures.append(
                f"line {line_number}: digest mismatch for {normalized!r}"
            )
            continue
        verified += 1
    return {
        "status": "PASS" if not failures and verified > 0 else "FAILED",
        "failures": failures,
        "verified": verified,
    }


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env),
        text=True,
        capture_output=True,
        check=False,
    )
    _atomic_write(stdout_path, completed.stdout.encode("utf-8"))
    _atomic_write(stderr_path, completed.stderr.encode("utf-8"))
    return completed.returncode


def _venv_python(environment_dir: Path) -> Path:
    if os.name == "nt":
        return environment_dir / ".venv" / "Scripts" / "python.exe"
    return environment_dir / ".venv" / "bin" / "python"


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
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    environment_dir = run_dir / "environment"
    environment_dir.mkdir()
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
        env["UV_FIND_LINKS"] = str(wheelhouse.resolve())
    if offline:
        env["UV_OFFLINE"] = "1"
    lock_command = [
        uv_executable,
        "lock",
        "--project",
        str(environment_dir),
        "--python",
        "3.13",
    ]
    lock_rc = _run_command(
        lock_command,
        cwd=repo_root,
        env=env,
        stdout_path=run_dir / "uv-lock.stdout.log",
        stderr_path=run_dir / "uv-lock.stderr.log",
    )
    commands.append(
        {"phase": "lock", "command": lock_command, "returncode": lock_rc}
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
        sync_rc = _run_command(
            sync_command,
            cwd=repo_root,
            env=env,
            stdout_path=run_dir / "uv-sync.stdout.log",
            stderr_path=run_dir / "uv-sync.stderr.log",
        )
        commands.append(
            {"phase": "sync", "command": sync_command, "returncode": sync_rc}
        )
    if sync_rc == 0:
        python = _venv_python(environment_dir)
        certification_output = run_dir / "certification"
        certification_command = [
            str(python),
            "-m",
            "loto.statsforecast.certify",
            "--output-root",
            str(certification_output),
            "--model-parameters",
            str(
                repo_root
                / "configs"
                / "statsforecast"
                / "runtime_parameters.json"
            ),
            "--horizon",
            str(horizon),
            "--seed",
            str(seed),
        ]
        cert_env = env.copy()
        cert_env["PYTHONPATH"] = str(repo_root / "src")
        certification_rc = _run_command(
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
                inner_run = Path(line.removeprefix("RUN_DIR=").strip())
                break
        if inner_run is not None:
            checksum_report = verify_portable_sha256sums(inner_run)
    status = (
        "PASS"
        if certification_rc == 0 and checksum_report["status"] == "PASS"
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
            str(wheelhouse.resolve()) if wheelhouse is not None else None
        ),
        "lock_returncode": lock_rc,
        "sync_returncode": sync_rc,
        "certification_returncode": certification_rc,
        "inner_run": str(inner_run) if inner_run is not None else None,
        "inner_checksum_verification": checksum_report,
        "holdout_opened": False,
        "prospective_actual_known": False,
        "finished_at_utc": _utc_now(),
    }
    _write_json(run_dir / "COMMANDS.json", commands)
    _write_json(run_dir / "RUNTIME_LANE_REPORT.json", report)
    return run_dir


__all__ = [
    "PYPI_JSON_URL",
    "TARGET_PACKAGE",
    "TARGET_VERSION",
    "execute_runtime_lane",
    "fetch_release_artifact",
    "select_compatible_release_file",
    "sha256_file",
    "verify_portable_sha256sums",
]
