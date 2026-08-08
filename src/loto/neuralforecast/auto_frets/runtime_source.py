"""Git and source-byte identity helpers for AutoFreTS runtime evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .runtime_contracts import SourceFileRecord

SOURCE_PATHS: tuple[str, ...] = (
    "src/loto/neuralforecast/auto_frets/__init__.py",
    "src/loto/neuralforecast/auto_frets/auto.py",
    "src/loto/neuralforecast/auto_frets/contracts.py",
    "src/loto/neuralforecast/auto_frets/model.py",
    "src/loto/neuralforecast/auto_frets/runtime.py",
    "src/loto/neuralforecast/auto_frets/runtime_contracts.py",
    "src/loto/neuralforecast/auto_frets/runtime_source.py",
    "src/loto/neuralforecast/auto_frets/runtime_worker.py",
    "src/loto/neuralforecast/auto_frets/runtime_certification.py",
    "src/loto/neuralforecast/auto_frets/certify.py",
)


class SourceIdentityError(RuntimeError):
    """Raised when the current checkout cannot be trusted for certification."""


@dataclass(frozen=True)
class PreparedSource:
    snapshot_root: Path
    source_revision: str
    source_tree_sha256: str
    files: tuple[SourceFileRecord, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    relative = candidate.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SourceIdentityError(f"source path contains a symlink: {relative.as_posix()}")


def collect_source_inventory(
    working_directory: Path,
    *,
    source_paths: Sequence[str] = SOURCE_PATHS,
) -> tuple[SourceFileRecord, ...]:
    root = working_directory.expanduser().resolve(strict=True)
    records: list[SourceFileRecord] = []
    for relative_path in source_paths:
        candidate = root / relative_path
        try:
            candidate.relative_to(root)
            _reject_symlink_components(root, candidate)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise SourceIdentityError(
                f"required source file is missing or escapes the repository: {relative_path}"
            ) from exc
        if not resolved.is_file():
            raise SourceIdentityError(f"required source is not a regular file: {relative_path}")
        records.append(
            SourceFileRecord(
                relative_path=relative_path,
                sha256=_sha256_file(resolved),
                size_bytes=resolved.stat().st_size,
            )
        )
    return tuple(records)


def canonical_source_tree_sha256(files: Sequence[SourceFileRecord]) -> str:
    rows = [item.model_dump(mode="json") for item in files]
    encoded = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_git(working_directory: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(working_directory), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise SourceIdentityError(f"git command failed: {message}")
    return completed.stdout.strip()


def verify_git_checkout(
    working_directory: Path,
    expected_revision: str,
    *,
    command_runner: Callable[[Path, list[str]], str] = _run_git,
) -> None:
    root = working_directory.expanduser().resolve(strict=True)
    actual_revision = command_runner(root, ["rev-parse", "HEAD"])
    if actual_revision != expected_revision:
        raise SourceIdentityError(
            f"Git HEAD mismatch: expected {expected_revision}, got {actual_revision}"
        )
    branch = command_runner(root, ["branch", "--show-current"])
    if not branch:
        raise SourceIdentityError("detached Git HEAD is not certifiable")
    status = command_runner(
        root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    )
    if status:
        raise SourceIdentityError("Git worktree must be completely clean")


def verify_working_source(
    working_directory: Path,
    *,
    expected_revision: str,
    expected_tree_sha256: str,
    command_runner: Callable[[Path, list[str]], str] = _run_git,
) -> tuple[SourceFileRecord, ...]:
    verify_git_checkout(
        working_directory,
        expected_revision,
        command_runner=command_runner,
    )
    files = collect_source_inventory(working_directory)
    actual_tree_sha256 = canonical_source_tree_sha256(files)
    if actual_tree_sha256 != expected_tree_sha256:
        raise SourceIdentityError(
            "AutoFreTS source-tree SHA-256 mismatch: "
            f"expected {expected_tree_sha256}, got {actual_tree_sha256}"
        )
    return files


def materialize_source_snapshot(
    working_directory: Path,
    output_parent: Path,
    *,
    source_revision: str,
    files: Sequence[SourceFileRecord],
) -> Path:
    root = working_directory.expanduser().resolve(strict=True)
    parent = output_parent.expanduser().resolve(strict=True)
    destination = parent / source_revision
    if destination.exists():
        raise SourceIdentityError(f"source snapshot already exists: {destination}")
    temporary = parent / f".{source_revision}.tmp-{os.getpid()}"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=False)
    try:
        for item in files:
            source = root / item.relative_path
            target = temporary / item.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            if target.stat().st_size != item.size_bytes or _sha256_file(target) != item.sha256:
                raise SourceIdentityError(
                    f"source snapshot copy verification failed: {item.relative_path}"
                )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination.resolve(strict=True)


def prepare_source_snapshot(
    working_directory: Path,
    output_parent: Path,
    *,
    expected_revision: str,
    expected_tree_sha256: str,
    command_runner: Callable[[Path, list[str]], str] = _run_git,
) -> PreparedSource:
    files = verify_working_source(
        working_directory,
        expected_revision=expected_revision,
        expected_tree_sha256=expected_tree_sha256,
        command_runner=command_runner,
    )
    snapshot_root = materialize_source_snapshot(
        working_directory,
        output_parent,
        source_revision=expected_revision,
        files=files,
    )
    return PreparedSource(
        snapshot_root=snapshot_root,
        source_revision=expected_revision,
        source_tree_sha256=expected_tree_sha256,
        files=tuple(files),
    )


__all__ = [
    "PreparedSource",
    "SOURCE_PATHS",
    "SourceIdentityError",
    "canonical_source_tree_sha256",
    "collect_source_inventory",
    "materialize_source_snapshot",
    "prepare_source_snapshot",
    "verify_git_checkout",
    "verify_working_source",
]
