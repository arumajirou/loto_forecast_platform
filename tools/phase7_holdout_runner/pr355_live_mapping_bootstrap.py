from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

PR_BRANCH: Final = "agent/phase7-holdout-runner-canonical-v1"
MATERIALIZED_PATHS: Final = (
    "tools/phase7_holdout_runner/live_mapping_key_diagnostic.py",
    "tools/phase7_holdout_runner/derive_canonical_runner.py",
    "src/loto/evaluation/semantic_config.py",
)


class BootstrapError(RuntimeError):
    """Raised when the isolated PR diagnostic bootstrap cannot run safely."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_worktree() -> Path:
    """Return a fresh isolated materialization root.

    The historical CLI option remains named ``--worktree`` for compatibility,
    but no Git worktree is created. Only the exact files required by the
    diagnostic are materialized with ``git show``.
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"loto-pr355-live-diagnostic-materialized-{stamp}"


def run_git(repo: Path, *args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        capture_output=capture,
    )


def fetch_pr_head(repo: Path) -> str:
    fetch = run_git(repo, "fetch", "origin", PR_BRANCH)
    if fetch.returncode != 0:
        raise BootstrapError(f"git fetch failed: {fetch.stderr.strip()}")

    resolved = run_git(repo, "rev-parse", "FETCH_HEAD")
    if resolved.returncode != 0:
        raise BootstrapError(f"FETCH_HEAD resolution failed: {resolved.stderr.strip()}")

    head = resolved.stdout.strip()
    if len(head) != 40:
        raise BootstrapError(f"unexpected FETCH_HEAD: {head!r}")
    return head


def git_show_bytes(repo: Path, head: str, path: str) -> bytes:
    run = subprocess.run(
        ["git", "-C", str(repo), "show", f"{head}:{path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if run.returncode != 0:
        stderr = run.stderr.decode("utf-8", errors="replace").strip()
        raise BootstrapError(f"git show failed for {path}: {stderr}")
    return bytes(run.stdout)


def materialize_pr_files(repo: Path, root: Path, head: str) -> None:
    if root.exists():
        raise BootstrapError(f"materialization path already exists: {root}")

    root.mkdir(parents=True, exist_ok=False)
    try:
        for relative in MATERIALIZED_PATHS:
            destination = root / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git_show_bytes(repo, head, relative))
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def remove_materialized_root(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


def run_bootstrap(*, repo: Path, worktree: Path, keep_worktree: bool) -> int:
    head = fetch_pr_head(repo)
    print(f"PR355_FETCHED_HEAD={head}")
    print("PRIMARY_WORKTREE_SWITCHED=NO")
    print("PRIMARY_WORKTREE_RESET=NO")
    print("PRIMARY_WORKTREE_CLEAN=NO")
    print("PRIMARY_WORKTREE_STASH=NO")
    print("WINDOWS_INVALID_PATH_CHECKOUT_AVOIDED=YES")

    materialize_pr_files(repo, worktree, head)
    print(f"ISOLATED_MATERIALIZED_ROOT={worktree}")
    print(f"SELECTIVE_FILE_COUNT={len(MATERIALIZED_PATHS)}")

    diagnostic = (
        worktree
        / "tools"
        / "phase7_holdout_runner"
        / "live_mapping_key_diagnostic.py"
    )
    if not diagnostic.is_file():
        if not keep_worktree:
            remove_materialized_root(worktree)
        raise BootstrapError(f"PR355 diagnostic script missing: {diagnostic}")

    try:
        run = subprocess.run(
            [sys.executable, str(diagnostic), "--repo-root", str(worktree)],
            check=False,
        )
        return_code = int(run.returncode)
    finally:
        if keep_worktree:
            print(f"ISOLATED_MATERIALIZED_ROOT_KEPT={worktree}")
        else:
            remove_materialized_root(worktree)
            print("ISOLATED_MATERIALIZED_ROOT_REMOVED=YES")

    return return_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch PR #355 and selectively materialize only the three files required for the "
            "live mapping-key diagnostic. This avoids Windows-invalid historical paths and "
            "does not switch, reset, clean, or stash the primary worktree."
        )
    )
    parser.add_argument("--repo", type=Path, default=repo_root())
    parser.add_argument(
        "--worktree",
        "--materialized-root",
        dest="worktree",
        type=Path,
        default=None,
        help="isolated materialization root; --worktree is retained for CLI compatibility",
    )
    parser.add_argument(
        "--keep-worktree",
        "--keep-materialized-root",
        dest="keep_worktree",
        action="store_true",
        help="keep the isolated materialized diagnostic files after execution",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worktree = args.worktree or default_worktree()
    return run_bootstrap(
        repo=args.repo.resolve(),
        worktree=worktree.resolve(),
        keep_worktree=args.keep_worktree,
    )


if __name__ == "__main__":
    raise SystemExit(main())
