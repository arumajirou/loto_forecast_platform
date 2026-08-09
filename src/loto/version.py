"""Application version and reproducible build metadata.

``__version__`` is the only application-version literal in the repository. Packaging,
APIs, dashboards, and CLIs consume this module rather than maintaining copies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

__version__ = "3.2.0"

DISTRIBUTION_NAME = "loto-forecast-platform"
BUILD_INFO_SCHEMA_VERSION = "1.0.0"
VERSION_SOURCE = "loto.version.__version__"
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class BuildInfo:
    """Version and build provenance with deliberately separate semantics."""

    schema_version: str
    package_version: str
    version_source: str
    installed_distribution_version: str | None
    installed_distribution_status: str
    git_commit: str
    git_dirty: bool | None
    build_time: str | None
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def installed_distribution_version(
    getter: Callable[[str], str] | None = None,
) -> str | None:
    """Return installed metadata version, or ``None`` in a source-only checkout."""

    resolve = getter or metadata.version
    try:
        return str(resolve(DISTRIBUTION_NAME))
    except metadata.PackageNotFoundError:
        return None


def installed_distribution_status(distribution_version: str | None) -> str:
    if distribution_version is None:
        return "SOURCE_ONLY"
    if distribution_version == __version__:
        return "MATCH"
    return "MISMATCH"


def _run_git(repo_root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _environment_commit(repo_root: str | Path | None = None) -> str | None:
    explicit = os.environ.get("LOTO_BUILD_GIT_COMMIT", "").strip()
    if explicit and _GIT_SHA_PATTERN.fullmatch(explicit):
        return explicit.lower()

    github_sha = os.environ.get("GITHUB_SHA", "").strip()
    if not github_sha or not _GIT_SHA_PATTERN.fullmatch(github_sha):
        return None
    if repo_root is None:
        return github_sha.lower()

    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if not workspace:
        return None
    if Path(repo_root).resolve() != Path(workspace).resolve():
        return None
    return github_sha.lower()


def resolve_git_commit(repo_root: str | Path | None = None) -> str:
    """Resolve Git identity without confusing absence with an empty commit."""

    environment_value = _environment_commit(repo_root)
    if environment_value is not None:
        return environment_value
    root = Path(repo_root or Path.cwd()).resolve()
    value = _run_git(root, "rev-parse", "HEAD")
    if value and _GIT_SHA_PATTERN.fullmatch(value):
        return value.lower()
    return "UNAVAILABLE"


def _parse_dirty_value(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def resolve_git_dirty(repo_root: str | Path | None = None) -> bool | None:
    """Return dirty state, or ``None`` when no reliable Git worktree is available."""

    environment_value = os.environ.get("LOTO_BUILD_GIT_DIRTY")
    if environment_value is not None:
        return _parse_dirty_value(environment_value)
    root = Path(repo_root or Path.cwd()).resolve()
    value = _run_git(root, "status", "--porcelain", "--untracked-files=normal")
    if value is None:
        return None
    return bool(value)


def _normalize_timestamp(value: str | None, *, label: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def collect_build_info(
    *,
    repo_root: str | Path | None = None,
    build_time: str | None = None,
    distribution_getter: Callable[[str], str] | None = None,
    generated_at: str | None = None,
) -> BuildInfo:
    """Collect build metadata without treating runtime time as build time."""

    distribution_version = installed_distribution_version(distribution_getter)
    explicit_build_time = build_time or os.environ.get("LOTO_BUILD_TIME")
    normalized_build_time = _normalize_timestamp(explicit_build_time, label="build_time")
    normalized_generated_at = _normalize_timestamp(generated_at, label="generated_at")
    if normalized_generated_at is None:
        normalized_generated_at = datetime.now(timezone.utc).isoformat()
    return BuildInfo(
        schema_version=BUILD_INFO_SCHEMA_VERSION,
        package_version=__version__,
        version_source=VERSION_SOURCE,
        installed_distribution_version=distribution_version,
        installed_distribution_status=installed_distribution_status(distribution_version),
        git_commit=resolve_git_commit(repo_root),
        git_dirty=resolve_git_dirty(repo_root),
        build_time=normalized_build_time,
        generated_at=normalized_generated_at,
    )


def write_build_info(
    output: str | Path,
    *,
    repo_root: str | Path | None = None,
    build_time: str | None = None,
    distribution_getter: Callable[[str], str] | None = None,
) -> BuildInfo:
    """Atomically write a ``BUILD_INFO.json``-compatible artifact."""

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    info = collect_build_info(
        repo_root=repo_root,
        build_time=build_time,
        distribution_getter=distribution_getter,
    )
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(info.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return info


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto-build-info")
    parser.add_argument("--output", default="BUILD_INFO.json")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--build-time")
    parser.add_argument("--require-installed-match", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    info = write_build_info(
        args.output,
        repo_root=args.repo_root,
        build_time=args.build_time,
    )
    print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_installed_match and info.installed_distribution_status == "MISMATCH":
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
