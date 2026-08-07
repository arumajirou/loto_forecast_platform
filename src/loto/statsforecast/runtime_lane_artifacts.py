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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, canonical_json(payload) + b"\n")


def run_command(
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
    atomic_write(stdout_path, completed.stdout.encode("utf-8"))
    atomic_write(stderr_path, completed.stderr.encode("utf-8"))
    return completed.returncode


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def release_files(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
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
    ordered_tags = tuple(supported_tags or sys_tags())
    tag_rank = {tag: rank for rank, tag in enumerate(ordered_tags)}
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    files = release_files(payload)
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


def fetch_release_metadata(
    *,
    metadata_url: str = PYPI_JSON_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    supported_tags: Iterable[Tag] | None = None,
) -> tuple[dict[str, Any], bytes]:
    with opener(metadata_url, timeout=60) as response:
        metadata_bytes = response.read()
    metadata = json.loads(metadata_bytes)
    selected = select_compatible_release_file(
        metadata,
        supported_tags=supported_tags,
    )
    return selected, metadata_bytes


def fetch_release_artifact(
    wheelhouse: Path,
    *,
    metadata_url: str = PYPI_JSON_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    supported_tags: Iterable[Tag] | None = None,
) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    selected, metadata_bytes = fetch_release_metadata(
        metadata_url=metadata_url,
        opener=opener,
        supported_tags=supported_tags,
    )
    with opener(selected["url"], timeout=180) as response:
        artifact_bytes = response.read()
    actual = sha256_bytes(artifact_bytes)
    if actual != selected["sha256"]:
        raise ValueError(
            f"downloaded artifact SHA-256 mismatch: "
            f"expected {selected['sha256']}, got {actual}"
        )
    artifact_path = wheelhouse / selected["filename"]
    atomic_write(artifact_path, artifact_bytes)
    write_json(
        wheelhouse / "PYPI_RELEASE_SELECTION.json",
        {
            "schema_version": 1,
            "package": TARGET_PACKAGE,
            "version": TARGET_VERSION,
            "metadata_url": metadata_url,
            "selected": selected,
            "metadata_sha256": sha256_bytes(metadata_bytes),
            "downloaded_sha256": actual,
            "downloaded_at_utc": utc_now(),
        },
    )
    selection_path = wheelhouse / "PYPI_RELEASE_SELECTION.json"
    sums = [
        f"{actual}  {artifact_path.name}",
        f"{sha256_file(selection_path)}  PYPI_RELEASE_SELECTION.json",
    ]
    atomic_write(
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
    for line_number, raw in enumerate(
        checksum_file.read_text(encoding="utf-8").splitlines(),
        1,
    ):
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
        if sha256_file(path) != digest:
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


def write_tree_sums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        ignored = path.name == "SHA256SUMS" or ".bootstrap-venv" in path.parts
        if path.is_file() and not ignored:
            relative = path.relative_to(root).as_posix()
            rows.append(f"{sha256_file(path)}  {relative}")
    atomic_write(
        root / "SHA256SUMS",
        ("\n".join(rows) + "\n").encode("utf-8"),
    )


def verify_offline_bundle(wheelhouse: Path) -> dict[str, Any]:
    checksum = verify_portable_sha256sums(wheelhouse)
    failures = list(checksum["failures"])
    required = [
        wheelhouse / "project" / "pyproject.toml",
        wheelhouse / "project" / "uv.lock",
        wheelhouse / "requirements.txt",
        wheelhouse / "PYPI_RELEASE_SELECTION.json",
    ]
    for path in required:
        if not path.is_file() or path.is_symlink():
            relative = path.relative_to(wheelhouse)
            failures.append(f"required bundle file missing: {relative}")
    packages = wheelhouse / "packages"
    if not packages.is_dir() or not any(packages.iterdir()):
        failures.append("packages directory is missing or empty")
    selection_path = wheelhouse / "PYPI_RELEASE_SELECTION.json"
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selected = selection.get("selected", {})
        filename = str(selected.get("filename", ""))
        digest = str(selected.get("sha256", ""))
        selected_path = packages / filename
        if not selected_path.is_file():
            failures.append(
                f"selected StatsForecast artifact is missing: {filename}"
            )
        elif sha256_file(selected_path) != digest:
            failures.append("selected StatsForecast artifact digest mismatch")
    return {
        "status": "PASS" if not failures else "FAILED",
        "failures": failures,
        "verified": checksum["verified"],
    }


def prepare_offline_bundle(
    repo_root: Path,
    wheelhouse: Path,
    *,
    uv_executable: str = "uv",
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=False)
    project = wheelhouse / "project"
    project.mkdir()
    template = (
        repo_root
        / "environments"
        / "statsforecast-py313"
        / "pyproject.toml"
    )
    shutil.copy2(template, project / "pyproject.toml")
    logs = wheelhouse / "build-logs"
    logs.mkdir()
    env = os.environ.copy()
    lock_command = [
        uv_executable,
        "lock",
        "--project",
        str(project),
        "--python",
        "3.13",
    ]
    lock_rc = run_command(
        lock_command,
        cwd=repo_root,
        env=env,
        stdout_path=logs / "uv-lock.stdout.log",
        stderr_path=logs / "uv-lock.stderr.log",
    )
    if lock_rc != 0:
        raise RuntimeError("uv lock failed while preparing offline bundle")
    requirements = wheelhouse / "requirements.txt"
    export_command = [
        uv_executable,
        "export",
        "--project",
        str(project),
        "--locked",
        "--format",
        "requirements.txt",
        "--no-dev",
        "--no-emit-project",
        "--output-file",
        str(requirements),
    ]
    export_rc = run_command(
        export_command,
        cwd=repo_root,
        env=env,
        stdout_path=logs / "uv-export.stdout.log",
        stderr_path=logs / "uv-export.stderr.log",
    )
    if export_rc != 0:
        raise RuntimeError("uv export failed while preparing offline bundle")
    bootstrap = wheelhouse / ".bootstrap-venv"
    venv_command = [
        uv_executable,
        "venv",
        "--python",
        "3.13",
        "--seed",
        str(bootstrap),
    ]
    venv_rc = run_command(
        venv_command,
        cwd=repo_root,
        env=env,
        stdout_path=logs / "uv-venv.stdout.log",
        stderr_path=logs / "uv-venv.stderr.log",
    )
    if venv_rc != 0:
        raise RuntimeError("uv venv failed while preparing offline bundle")
    packages = wheelhouse / "packages"
    packages.mkdir()
    download_command = [
        str(venv_python(bootstrap)),
        "-m",
        "pip",
        "download",
        "--require-hashes",
        "--requirement",
        str(requirements),
        "--dest",
        str(packages),
    ]
    download_rc = run_command(
        download_command,
        cwd=repo_root,
        env=env,
        stdout_path=logs / "pip-download.stdout.log",
        stderr_path=logs / "pip-download.stderr.log",
    )
    shutil.rmtree(bootstrap, ignore_errors=True)
    if download_rc != 0:
        raise RuntimeError("pip download failed while preparing offline bundle")
    selected, metadata_bytes = fetch_release_metadata(opener=opener)
    selected_path = packages / selected["filename"]
    if not selected_path.is_file():
        raise RuntimeError(
            "pip download did not produce the selected StatsForecast wheel"
        )
    actual = sha256_file(selected_path)
    if actual != selected["sha256"]:
        raise RuntimeError(
            "downloaded StatsForecast wheel does not match PyPI SHA-256"
        )
    write_json(
        wheelhouse / "PYPI_RELEASE_SELECTION.json",
        {
            "schema_version": 1,
            "package": TARGET_PACKAGE,
            "version": TARGET_VERSION,
            "metadata_url": PYPI_JSON_URL,
            "selected": selected,
            "metadata_sha256": sha256_bytes(metadata_bytes),
            "downloaded_sha256": actual,
            "prepared_at_utc": utc_now(),
        },
    )
    package_count = len(
        [path for path in packages.iterdir() if path.is_file()]
    )
    write_json(
        wheelhouse / "OFFLINE_BUNDLE_REPORT.json",
        {
            "schema_version": 1,
            "status": "PASS",
            "python_lane": "3.13",
            "target_package": TARGET_PACKAGE,
            "target_version": TARGET_VERSION,
            "package_file_count": package_count,
            "prepared_at_utc": utc_now(),
        },
    )
    write_tree_sums(wheelhouse)
    verification = verify_offline_bundle(wheelhouse)
    if verification["status"] != "PASS":
        failures = verification["failures"]
        raise RuntimeError(
            f"offline bundle verification failed: {failures}"
        )
    return wheelhouse


__all__ = [
    "PYPI_JSON_URL",
    "TARGET_PACKAGE",
    "TARGET_VERSION",
    "atomic_write",
    "fetch_release_artifact",
    "fetch_release_metadata",
    "prepare_offline_bundle",
    "run_command",
    "select_compatible_release_file",
    "sha256_file",
    "utc_now",
    "venv_python",
    "verify_offline_bundle",
    "verify_portable_sha256sums",
    "write_json",
]
