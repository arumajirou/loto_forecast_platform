from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from loto.mlforecast.artifacts import sha256_bytes, sha256_file
from loto.mlforecast.handoff import (
    FIXED_ZIP_DATETIME,
    HANDOFF_FORMAT,
    OPTIONAL_DOCUMENTS,
    REQUIRED_DOCUMENTS,
    REQUIRED_PROVENANCE_DOCUMENTS,
    SCOPED_PATHS,
    HandoffResult,
    build_handoff_bundle,
)
from loto.mlforecast.provenance import upstream_contract


DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
SHARED_SNAPSHOT_PATHS = ("pyproject.toml", "uv.lock")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
REQUIRED_CONFIG_FILES = (
    "configs/mlforecast/auto.yaml",
    "configs/mlforecast/core.yaml",
)
REQUIRED_OPERATIONAL_FILES = (
    "docs/mlforecast/build_handoff_bundle.sh",
    "docs/mlforecast/run_runtime_certification.sh",
)
REQUIRED_SOURCE_FILES = (
    "src/loto/mlforecast/__init__.py",
    "src/loto/mlforecast/artifacts.py",
    "src/loto/mlforecast/bundle.py",
    "src/loto/mlforecast/certify.py",
    "src/loto/mlforecast/cli.py",
    "src/loto/mlforecast/contracts.py",
    "src/loto/mlforecast/data.py",
    "src/loto/mlforecast/factory.py",
    "src/loto/mlforecast/handoff.py",
    "src/loto/mlforecast/handoff_guard.py",
    "src/loto/mlforecast/metrics.py",
    "src/loto/mlforecast/provenance.py",
    "src/loto/mlforecast/runner.py",
    "src/loto/mlforecast/runtime.py",
)
REQUIRED_TEST_FILES = (
    "tests/mlforecast/test_bundle.py",
    "tests/mlforecast/test_certify.py",
    "tests/mlforecast/test_contracts.py",
    "tests/mlforecast/test_factory.py",
    "tests/mlforecast/test_handoff.py",
    "tests/mlforecast/test_handoff_guard.py",
    "tests/mlforecast/test_metrics.py",
    "tests/mlforecast/test_provenance.py",
    "tests/mlforecast/test_runner_contracts.py",
    "tests/mlforecast/test_runtime_smoke.py",
)


@dataclass(frozen=True)
class RepositoryState:
    commit: str
    branch: str
    committed_at: str


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(
            f"git command failed: {' '.join(args)}: {detail.strip()}"
        ) from exc


def _valid_commit(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or COMMIT_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"{label} must be a 40-character lowercase hexadecimal SHA")
    return value


def _valid_branch(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value == "HEAD"
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeError(f"{label} must be a non-detached printable branch name")
    return value


def _valid_timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} must include a timezone offset")
    return value


def _raw_regular_file(path: Path, *, label: str) -> Path:
    raw = path.expanduser().absolute()
    if raw.is_symlink() or not raw.is_file():
        raise RuntimeError(f"{label} is not a regular file: {raw}")
    return raw.resolve()


def _repository_state(repo_root: Path) -> RepositoryState:
    raw_root = repo_root.expanduser().absolute()
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise RuntimeError(f"repository root is not a regular directory: {raw_root}")
    root = raw_root.resolve()
    top = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise RuntimeError(f"repository root mismatch: expected={root}, actual={top}")
    status = _run_git(
        root,
        "status",
        "--porcelain",
        "--",
        *SCOPED_PATHS,
        *SHARED_SNAPSHOT_PATHS,
    )
    if status:
        raise RuntimeError(
            "MLForecast handoff inputs are dirty; commit or clean them first:\n"
            f"{status}"
        )
    for shared in SHARED_SNAPSHOT_PATHS:
        _run_git(root, "ls-files", "--error-unmatch", shared)
    return RepositoryState(
        commit=_valid_commit(
            _run_git(root, "rev-parse", "HEAD"),
            label="repository HEAD",
        ),
        branch=_valid_branch(
            _run_git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            label="repository branch",
        ),
        committed_at=_valid_timestamp(
            _run_git(root, "show", "-s", "--format=%cI", "HEAD"),
            label="repository commit timestamp",
        ),
    )


def build_guarded_handoff(repo_root: Path, output_dir: Path) -> HandoffResult:
    before = _repository_state(repo_root)
    result = build_handoff_bundle(repo_root, output_dir)
    after = _repository_state(repo_root)
    if after != before or result.source_commit != before.commit:
        result.zip_path.unlink(missing_ok=True)
        result.sha256_path.unlink(missing_ok=True)
        raise RuntimeError(
            "repository state changed during handoff construction: "
            f"before={before}, after={after}, result={result.source_commit}"
        )
    return result


def _safe_path(value: str) -> PurePosixPath:
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeError(f"unsafe handoff archive path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise RuntimeError(f"unsafe handoff archive path: {value!r}")
    for part in path.parts:
        base = part.split(".", 1)[0].casefold()
        if (
            ":" in part
            or part.endswith((" ", "."))
            or base in WINDOWS_RESERVED_NAMES
        ):
            raise RuntimeError(f"non-portable handoff archive path: {value!r}")
    return path


def _sidecar_digest(sidecar: Path, zip_path: Path) -> str:
    lines = sidecar.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RuntimeError("handoff sidecar must contain exactly one line")
    digest, separator, name = lines[0].partition("  ")
    if (
        separator != "  "
        or name != zip_path.name
        or DIGEST_PATTERN.fullmatch(digest) is None
    ):
        raise RuntimeError("invalid handoff sidecar format")
    return digest


def _required_paths() -> set[str]:
    return (
        set(REQUIRED_DOCUMENTS)
        | set(REQUIRED_PROVENANCE_DOCUMENTS)
        | set(OPTIONAL_DOCUMENTS)
        | set(REQUIRED_CONFIG_FILES)
        | set(REQUIRED_OPERATIONAL_FILES)
        | set(REQUIRED_SOURCE_FILES)
        | set(REQUIRED_TEST_FILES)
        | {
            "repository/pyproject.toml",
            "repository/uv.lock",
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
            "SOURCE_PROVENANCE.json",
            "VERSION",
        }
    )


def verify_guarded_handoff(
    zip_path: Path,
    sha256_path: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    if max_files < 1 or max_uncompressed_bytes < 1:
        raise ValueError("handoff archive limits must be positive")
    resolved_zip = _raw_regular_file(zip_path, label="handoff ZIP")
    resolved_sidecar = _raw_regular_file(
        sha256_path,
        label="handoff sidecar",
    )
    expected_digest = _sidecar_digest(resolved_sidecar, resolved_zip)
    actual_digest = sha256_file(resolved_zip)
    if actual_digest != expected_digest:
        raise RuntimeError("handoff ZIP SHA-256 mismatch")

    with zipfile.ZipFile(resolved_zip) as archive:
        infos = archive.infolist()
        if len(infos) > max_files:
            raise RuntimeError(
                f"handoff ZIP exceeds file limit: {len(infos)} > {max_files}"
            )
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > max_uncompressed_bytes:
            raise RuntimeError(
                "handoff ZIP exceeds uncompressed-size limit: "
                f"{total_uncompressed} > {max_uncompressed_bytes}"
            )
        names = [info.filename for info in infos]
        if names != sorted(names) or len(names) != len(set(names)):
            raise RuntimeError("handoff ZIP entries must be unique and sorted")
        for info in infos:
            _safe_path(info.filename)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError(f"unsafe handoff ZIP member: {info.filename}")
            if info.flag_bits & 0x1:
                raise RuntimeError(f"encrypted handoff ZIP member: {info.filename}")
            if info.date_time != FIXED_ZIP_DATETIME:
                raise RuntimeError(f"non-deterministic ZIP timestamp: {info.filename}")
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"handoff ZIP CRC verification failed: {bad_member}")

        missing = sorted(_required_paths() - set(names))
        if missing:
            raise RuntimeError(f"handoff ZIP missing required artifacts: {missing}")

        try:
            manifest = json.loads(archive.read("ARTIFACT_MANIFEST.json"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid ARTIFACT_MANIFEST.json") from exc
        if not isinstance(manifest, dict):
            raise RuntimeError("ARTIFACT_MANIFEST.json must contain an object")
        if manifest.get("handoff_format") != HANDOFF_FORMAT:
            raise RuntimeError("unsupported handoff manifest format")
        manifest_commit = _valid_commit(
            manifest.get("source_commit"),
            label="handoff manifest source_commit",
        )
        records = manifest.get("artifacts")
        if not isinstance(records, list):
            raise RuntimeError("handoff manifest artifacts must be a list")

        expected: dict[str, str] = {}
        for record in records:
            if not isinstance(record, dict):
                raise RuntimeError("handoff manifest records must be objects")
            name = record.get("path")
            size = record.get("size_bytes")
            digest = record.get("sha256")
            if not isinstance(name, str) or name in expected:
                raise RuntimeError("invalid or duplicate handoff manifest path")
            _safe_path(name)
            if not isinstance(size, int) or size < 0:
                raise RuntimeError(f"invalid handoff manifest size: {name}")
            if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest) is None:
                raise RuntimeError(f"invalid handoff manifest SHA-256: {name}")
            try:
                payload = archive.read(name)
            except KeyError as exc:
                raise RuntimeError(f"handoff manifest member missing: {name}") from exc
            if len(payload) != size or sha256_bytes(payload) != digest:
                raise RuntimeError(f"handoff manifest verification failed: {name}")
            expected[name] = digest

        exact_names = set(expected) | {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
        if set(names) != exact_names:
            extra = sorted(set(names) - exact_names)
            absent = sorted(exact_names - set(names))
            raise RuntimeError(
                "handoff ZIP file set differs from manifest contract: "
                f"extra={extra}, missing={absent}"
            )

        sums: dict[str, str] = {}
        for line in archive.read("SHA256SUMS").decode("utf-8").splitlines():
            digest, separator, name = line.partition("  ")
            if (
                separator != "  "
                or name in sums
                or DIGEST_PATTERN.fullmatch(digest) is None
            ):
                raise RuntimeError("invalid handoff SHA256SUMS")
            _safe_path(name)
            sums[name] = digest
        if sums != expected:
            raise RuntimeError("handoff SHA256SUMS does not match manifest")

        try:
            provenance = json.loads(archive.read("SOURCE_PROVENANCE.json"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid SOURCE_PROVENANCE.json") from exc
        if not isinstance(provenance, dict):
            raise RuntimeError("SOURCE_PROVENANCE.json must contain an object")
        if provenance.get("handoff_format") != HANDOFF_FORMAT:
            raise RuntimeError("unsupported source provenance format")
        if provenance.get("source_commit") != manifest_commit:
            raise RuntimeError(
                "source commit disagrees between manifest and provenance"
            )
        source_branch = _valid_branch(
            provenance.get("source_branch"),
            label="source provenance branch",
        )
        _valid_timestamp(
            provenance.get("source_committed_at"),
            label="source provenance timestamp",
        )
        frozen_base = _valid_commit(
            provenance.get("frozen_base_sha"),
            label="source provenance frozen base SHA",
        )
        frozen_base_file = archive.read("FROZEN_BASE_SHA").decode("utf-8").strip()
        if frozen_base_file != frozen_base:
            raise RuntimeError("FROZEN_BASE_SHA disagrees with source provenance")

        try:
            frozen_upstream = json.loads(archive.read("FROZEN_UPSTREAM.json"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid FROZEN_UPSTREAM.json") from exc
        if not isinstance(frozen_upstream, dict):
            raise RuntimeError("FROZEN_UPSTREAM.json must contain an object")
        expected_upstream = upstream_contract()
        if provenance.get("mlforecast_upstream") != expected_upstream:
            raise RuntimeError("source provenance upstream contract mismatch")
        for key, expected_value in expected_upstream.items():
            if frozen_upstream.get(key) != expected_value:
                raise RuntimeError(f"FROZEN_UPSTREAM.json mismatch for {key}")
        if provenance.get("scope") != list(SCOPED_PATHS):
            raise RuntimeError("source provenance scope mismatch")
        if provenance.get("shared_environment_snapshots") != [
            "repository/pyproject.toml",
            "repository/uv.lock",
        ]:
            raise RuntimeError("source provenance shared snapshot list mismatch")
        version = archive.read("VERSION").decode("utf-8")
        if version != f"mlforecast-handoff-{manifest_commit[:12]}\n":
            raise RuntimeError("VERSION does not match source commit")

    return {
        "status": "HANDOFF_VERIFIED",
        "zip_path": str(resolved_zip),
        "sha256": actual_digest,
        "source_commit": manifest_commit,
        "source_branch": source_branch,
        "file_count": len(names),
        "uncompressed_bytes": total_uncompressed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast-handoff-guard",
        description="Build or strictly verify an MLForecast source handoff bundle",
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
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument(
        "--max-uncompressed-bytes",
        type=int,
        default=DEFAULT_MAX_UNCOMPRESSED_BYTES,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.build:
        result = build_guarded_handoff(args.repo_root, args.output_dir)
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
        payload = verify_guarded_handoff(
            args.zip_path,
            args.sha256_path,
            max_files=args.max_files,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
