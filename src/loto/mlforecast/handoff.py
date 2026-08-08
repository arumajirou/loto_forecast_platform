from __future__ import annotations

import argparse
import json
import stat
import subprocess
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.artifacts import atomic_write_text, sha256_bytes, sha256_file
from loto.mlforecast.provenance import upstream_contract

FIXED_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)
HANDOFF_FORMAT = 1
REQUIRED_DOCUMENTS = (
    "README.md",
    "REQUIREMENTS.md",
    "SPECIFICATION.md",
    "ARCHITECTURE.md",
    "DATA_CONTRACT.md",
    "TEST_PLAN.md",
    "VERIFICATION_REPORT.md",
    "CHANGELOG.md",
    "HANDOFF.md",
    "RUNBOOK.md",
)
REQUIRED_PROVENANCE_DOCUMENTS = (
    "FROZEN_BASE_SHA",
    "FROZEN_UPSTREAM.json",
)
OPTIONAL_DOCUMENTS = (
    "RUNTIME_CERTIFICATION.md",
    "BUNDLE_VERIFICATION.md",
)
SCOPED_PATHS = (
    "configs/mlforecast",
    "docs/mlforecast",
    "src/loto/mlforecast",
    "tests/mlforecast",
)


@dataclass(frozen=True)
class HandoffResult:
    source_commit: str
    zip_path: Path
    sha256_path: Path
    sha256: str
    file_count: int


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(f"git command failed: {' '.join(args)}: {detail.strip()}") from exc


def _validate_repo(repo_root: Path) -> tuple[str, str, str]:
    root = repo_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"repository root not found: {root}")
    top_level = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    if top_level != root:
        raise RuntimeError(f"repository root mismatch: expected={root}, git={top_level}")
    status = _run_git(root, "status", "--porcelain", "--", *SCOPED_PATHS)
    if status:
        raise RuntimeError(
            f"MLForecast handoff scope is dirty; commit or clean these paths first:\n{status}"
        )
    commit = _run_git(root, "rev-parse", "HEAD")
    branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    committed_at = _run_git(root, "show", "-s", "--format=%cI", "HEAD")
    return commit, branch, committed_at


def _safe_archive_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise RuntimeError(f"unsafe handoff archive path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise RuntimeError(f"unsafe handoff archive path: {value!r}")
    return path


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATETIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = stat.S_IFREG << 16 | 0o644 << 16
    return info


def _iter_files(root: Path, relative_dir: str) -> Iterable[tuple[str, Path]]:
    base = root / relative_dir
    if not base.is_dir():
        raise FileNotFoundError(f"required handoff directory not found: {relative_dir}")
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"handoff scope contains symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        _safe_archive_path(relative)
        yield relative, path


def _tracked_scope_files(repo_root: Path) -> list[str]:
    try:
        payload = subprocess.check_output(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", *SCOPED_PATHS],
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        message = str(detail).strip()
        raise RuntimeError(f"unable to list tracked MLForecast files: {message}") from exc
    values = [value.decode("utf-8") for value in payload.split(b"\0") if value]
    if not values:
        raise RuntimeError("no tracked MLForecast files were found")
    return sorted(values)


def _payload_files(
    repo_root: Path,
    *,
    tracked_paths: list[str] | None = None,
) -> list[tuple[str, Path]]:
    docs_root = repo_root / "docs" / "mlforecast"
    required_docs = REQUIRED_DOCUMENTS + REQUIRED_PROVENANCE_DOCUMENTS
    missing = [name for name in required_docs if not (docs_root / name).is_file()]
    if missing:
        raise RuntimeError(f"required handoff documents are missing: {missing}")

    records: list[tuple[str, Path]] = []
    top_level_docs = (
        set(REQUIRED_DOCUMENTS) | set(REQUIRED_PROVENANCE_DOCUMENTS) | set(OPTIONAL_DOCUMENTS)
    )
    if tracked_paths is None:
        for relative_dir in ("configs/mlforecast", "src/loto/mlforecast", "tests/mlforecast"):
            records.extend(_iter_files(repo_root, relative_dir))
        candidate_docs = [path for path in sorted(docs_root.rglob("*")) if path.is_file()]
    else:
        candidate_docs = []
        for relative_value in tracked_paths:
            relative = _safe_archive_path(relative_value)
            source_path = repo_root.joinpath(*relative.parts)
            if source_path.is_symlink() or not source_path.is_file():
                raise RuntimeError(f"tracked handoff path is not a regular file: {relative_value}")
            if relative_value.startswith("docs/mlforecast/"):
                candidate_docs.append(source_path)
            else:
                records.append((relative_value, source_path))

    for path in candidate_docs:
        if path.is_symlink():
            raise RuntimeError(f"handoff scope contains symlink: {path}")
        if path.parent == docs_root and path.name in top_level_docs:
            archive_path = path.name
        else:
            archive_path = path.relative_to(repo_root).as_posix()
        _safe_archive_path(archive_path)
        records.append((archive_path, path))

    for shared in ("pyproject.toml", "uv.lock"):
        path = repo_root / shared
        if not path.is_file():
            raise FileNotFoundError(f"shared environment snapshot missing: {shared}")
        records.append((f"repository/{shared}", path))

    deduplicated: dict[str, Path] = {}
    for archive_path, source_path in records:
        if archive_path in deduplicated:
            raise RuntimeError(f"duplicate handoff archive path: {archive_path}")
        deduplicated[archive_path] = source_path
    return sorted(deduplicated.items())


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _build_entries(
    repo_root: Path,
    *,
    source_commit: str,
    source_branch: str,
    committed_at: str,
    tracked_paths: list[str] | None = None,
) -> list[tuple[str, bytes]]:
    source_records: list[dict[str, Any]] = []
    entries: list[tuple[str, bytes]] = []
    for archive_path, source_path in _payload_files(
        repo_root,
        tracked_paths=tracked_paths,
    ):
        payload = source_path.read_bytes()
        entries.append((archive_path, payload))
        source_records.append(
            {
                "path": archive_path,
                "size_bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )

    frozen_base = (
        (repo_root / "docs" / "mlforecast" / "FROZEN_BASE_SHA").read_text(encoding="utf-8").strip()
    )
    provenance = {
        "handoff_format": HANDOFF_FORMAT,
        "source_commit": source_commit,
        "source_branch": source_branch,
        "source_committed_at": committed_at,
        "frozen_base_sha": frozen_base,
        "mlforecast_upstream": upstream_contract(),
        "scope": list(SCOPED_PATHS),
        "shared_environment_snapshots": ["repository/pyproject.toml", "repository/uv.lock"],
        "shared_scope_notice": (
            "The snapshots are included for review and reproduction only. "
            "This PR does not modify shared dependency files."
        ),
    }
    entries.append(("SOURCE_PROVENANCE.json", _canonical_json(provenance)))
    entries.append(("VERSION", f"mlforecast-handoff-{source_commit[:12]}\n".encode()))

    manifest_records = [
        {
            "path": name,
            "size_bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
        for name, payload in sorted(entries)
    ]
    manifest = {
        "handoff_format": HANDOFF_FORMAT,
        "source_commit": source_commit,
        "artifacts": manifest_records,
    }
    entries.append(("ARTIFACT_MANIFEST.json", _canonical_json(manifest)))
    sums = "".join(f"{record['sha256']}  {record['path']}\n" for record in manifest_records).encode(
        "utf-8"
    )
    entries.append(("SHA256SUMS", sums))
    return sorted(entries)


def build_handoff_bundle(
    repo_root: Path,
    output_dir: Path,
    *,
    source_commit: str | None = None,
    source_branch: str | None = None,
    committed_at: str | None = None,
    validate_git: bool = True,
) -> HandoffResult:
    repo_root = repo_root.resolve()
    tracked_paths: list[str] | None = None
    if validate_git:
        git_commit, git_branch, git_committed_at = _validate_repo(repo_root)
        tracked_paths = _tracked_scope_files(repo_root)
        for shared in ("pyproject.toml", "uv.lock"):
            _run_git(repo_root, "ls-files", "--error-unmatch", shared)
        source_commit = source_commit or git_commit
        source_branch = source_branch or git_branch
        committed_at = committed_at or git_committed_at
    if not source_commit or len(source_commit) < 12:
        raise ValueError("source_commit must contain at least 12 characters")
    if not source_branch:
        raise ValueError("source_branch is required")
    if not committed_at:
        raise ValueError("committed_at is required")

    entries = _build_entries(
        repo_root,
        source_commit=source_commit,
        source_branch=source_branch,
        committed_at=committed_at,
        tracked_paths=tracked_paths,
    )
    output_dir = output_dir.resolve()
    if output_dir == repo_root or repo_root in output_dir.parents:
        allowed = repo_root / "artifacts" / "mlforecast-handoff"
        if output_dir != allowed.resolve():
            raise RuntimeError(
                "handoff output inside the repository must use artifacts/mlforecast-handoff"
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    short = source_commit[:12]
    zip_path = output_dir / f"mlforecast-handoff-{short}.zip"
    sha256_path = output_dir / f"mlforecast-handoff-{short}.zip.sha256"
    if zip_path.exists() or sha256_path.exists():
        raise FileExistsError(f"handoff bundle already exists for commit {source_commit}")

    temporary = zip_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, payload in entries:
                archive.writestr(_zip_info(name), payload)
        temporary.replace(zip_path)
    finally:
        temporary.unlink(missing_ok=True)

    digest = sha256_file(zip_path)
    atomic_write_text(sha256_path, f"{digest}  {zip_path.name}\n")
    return HandoffResult(
        source_commit=source_commit,
        zip_path=zip_path,
        sha256_path=sha256_path,
        sha256=digest,
        file_count=len(entries),
    )


def verify_handoff_bundle(zip_path: Path, sha256_path: Path) -> dict[str, Any]:
    zip_path = zip_path.resolve()
    sha256_path = sha256_path.resolve()
    expected_line = sha256_path.read_text(encoding="utf-8").strip()
    expected_digest, separator, expected_name = expected_line.partition("  ")
    if separator != "  " or expected_name != zip_path.name:
        raise RuntimeError("invalid handoff sidecar format")
    actual_digest = sha256_file(zip_path)
    if actual_digest != expected_digest:
        raise RuntimeError("handoff ZIP SHA-256 mismatch")

    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if names != sorted(names) or len(names) != len(set(names)):
            raise RuntimeError("handoff ZIP entries must be unique and sorted")
        for info in infos:
            _safe_archive_path(info.filename)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError(f"unsafe handoff ZIP member: {info.filename}")
            if info.flag_bits & 0x1:
                raise RuntimeError(f"encrypted handoff ZIP member: {info.filename}")
            if info.date_time != FIXED_ZIP_DATETIME:
                raise RuntimeError(f"non-deterministic ZIP timestamp: {info.filename}")
        required_names = (
            set(REQUIRED_DOCUMENTS)
            | set(REQUIRED_PROVENANCE_DOCUMENTS)
            | {
                "ARTIFACT_MANIFEST.json",
                "SHA256SUMS",
                "SOURCE_PROVENANCE.json",
                "VERSION",
            }
        )
        missing = sorted(required_names - set(names))
        if missing:
            raise RuntimeError(f"handoff ZIP missing required artifacts: {missing}")

        manifest = json.loads(archive.read("ARTIFACT_MANIFEST.json"))
        records = manifest.get("artifacts")
        if not isinstance(records, list):
            raise RuntimeError("invalid handoff artifact manifest")
        expected: dict[str, str] = {}
        for record in records:
            name = record.get("path")
            size = record.get("size_bytes")
            digest = record.get("sha256")
            if not isinstance(name, str) or name in expected:
                raise RuntimeError("invalid or duplicate handoff manifest path")
            payload = archive.read(name)
            if len(payload) != size or sha256_bytes(payload) != digest:
                raise RuntimeError(f"handoff manifest verification failed: {name}")
            expected[name] = digest
        sums: dict[str, str] = {}
        for line in archive.read("SHA256SUMS").decode("utf-8").splitlines():
            digest, separator, name = line.partition("  ")
            if separator != "  " or name in sums:
                raise RuntimeError("invalid handoff SHA256SUMS")
            sums[name] = digest
        if sums != expected:
            raise RuntimeError("handoff SHA256SUMS does not match manifest")
        provenance = json.loads(archive.read("SOURCE_PROVENANCE.json"))
    return {
        "status": "HANDOFF_VERIFIED",
        "zip_path": str(zip_path),
        "sha256": actual_digest,
        "source_commit": provenance.get("source_commit"),
        "source_branch": provenance.get("source_branch"),
        "file_count": len(names),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast-handoff",
        description="Build or verify a deterministic MLForecast source handoff bundle",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/mlforecast-handoff"),
    )
    parser.add_argument("--zip", dest="zip_path", type=Path)
    parser.add_argument("--sha256", dest="sha256_path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.build:
        result = build_handoff_bundle(args.repo_root, args.output_dir)
        payload = {
            "status": "HANDOFF_BUILT",
            "source_commit": result.source_commit,
            "zip_path": str(result.zip_path),
            "sha256_path": str(result.sha256_path),
            "sha256": result.sha256,
            "file_count": result.file_count,
        }
    else:
        if args.zip_path is None or args.sha256_path is None:
            raise SystemExit("--verify requires --zip and --sha256")
        payload = verify_handoff_bundle(args.zip_path, args.sha256_path)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
