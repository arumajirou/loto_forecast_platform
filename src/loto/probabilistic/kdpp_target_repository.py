from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

from loto.probabilistic.kdpp_certification_gate import sha256_file
from loto.probabilistic.kdpp_target_contracts import (
    RepositoryIdentity,
    _EXPORTER_FILES,
    _KDPP_FILES,
)


def _run(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {command!r}; returncode={completed.returncode}; "
            f"stderr={completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _is_within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    parent = root.resolve()
    return resolved == parent or parent in resolved.parents


def _inspect_repository(
    root: Path,
    *,
    role: Literal["exporter", "kdpp"],
    expected_head: str,
    python_executable: Path,
    required_files: tuple[str, ...],
) -> RepositoryIdentity:
    root = root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"{role} repository root is missing or unsafe")
    resolved_python = python_executable.resolve()
    if not resolved_python.is_file():
        raise ValueError(f"{role} Python executable is missing")
    if not os.access(resolved_python, os.X_OK):
        raise ValueError(f"{role} Python executable is not executable")
    actual_head = _run(["git", "rev-parse", "HEAD"], cwd=root)
    if actual_head != expected_head:
        raise ValueError(f"{role} repository HEAD mismatch")
    status = _run(["git", "status", "--porcelain"], cwd=root)
    if status:
        raise ValueError(f"{role} repository must be completely clean")
    branch = _run(["git", "branch", "--show-current"], cwd=root)
    if not branch:
        raise ValueError(f"{role} repository must not be detached")
    hashes: dict[str, str] = {}
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required {role} file is missing or unsafe: {relative}")
        hashes[relative] = sha256_file(path)
    return RepositoryIdentity(
        role=role,
        root=str(root),
        expected_head=expected_head,
        actual_head=actual_head,
        branch=branch,
        clean=True,
        python_executable=str(resolved_python),
        file_sha256=hashes,
    )


def _recheck_repository(identity: RepositoryIdentity) -> None:
    required = _EXPORTER_FILES if identity.role == "exporter" else _KDPP_FILES
    current = _inspect_repository(
        Path(identity.root),
        role=identity.role,
        expected_head=identity.expected_head,
        python_executable=Path(identity.python_executable),
        required_files=required,
    )
    if current != identity:
        raise ValueError(f"{identity.role} repository identity changed")


