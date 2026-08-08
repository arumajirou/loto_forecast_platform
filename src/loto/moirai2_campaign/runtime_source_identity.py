from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class RuntimeSourceIdentityError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo_root: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip()
        raise RuntimeSourceIdentityError(f"git {' '.join(arguments)} failed: {message}")
    return process.stdout.strip()


def capture_source_identity(
    *,
    repo_root: Path,
    principal_paths: Iterable[str],
) -> dict[str, Any]:
    root = repo_root.resolve()
    if not (root / ".git").exists() and not _git(root, "rev-parse", "--git-dir"):
        raise RuntimeSourceIdentityError(f"not a git repository: {root}")
    commit_sha = _git(root, "rev-parse", "HEAD")
    tree_sha = _git(root, "rev-parse", "HEAD^{tree}")
    status_text = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    changed_paths = [line[3:] for line in status_text.splitlines() if len(line) >= 4]
    if changed_paths:
        raise RuntimeSourceIdentityError(
            f"runtime campaign requires a clean worktree: {changed_paths}"
        )
    paths = tuple(sorted(set(principal_paths)))
    if not paths:
        raise RuntimeSourceIdentityError("principal source paths are required")
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise RuntimeSourceIdentityError(f"principal source files are missing: {missing}")
    file_hashes = {path: sha256_file(root / path) for path in paths}
    return {
        "schema_version": "moirai2-source-identity-v1",
        "repo_root": str(root),
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "worktree_clean": True,
        "changed_paths": [],
        "principal_file_sha256": file_hashes,
    }
