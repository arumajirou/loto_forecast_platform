from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

PR_BRANCH: Final = "agent/phase7-holdout-runner-canonical-v1"


class BootstrapError(RuntimeError):
    """Raised when the isolated PR diagnostic bootstrap cannot run safely."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_worktree() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"loto-pr355-live-diagnostic-worktree-{stamp}"


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


def add_detached_worktree(repo: Path, worktree: Path, head: str) -> None:
    if worktree.exists():
        raise BootstrapError(f"worktree path already exists: {worktree}")

    added = run_git(repo, "worktree", "add", "--detach", str(worktree), head)
    if added.returncode != 0:
        raise BootstrapError(f"git worktree add failed: {added.stderr.strip()}")


def remove_worktree(repo: Path, worktree: Path) -> None:
    removed = run_git(repo, "worktree", "remove", str(worktree))
    if removed.returncode != 0:
        raise BootstrapError(
            "diagnostic completed but temporary worktree removal failed: "
            f"{removed.stderr.strip()} ; path={worktree}"
        )


def run_bootstrap(*, repo: Path, worktree: Path, keep_worktree: bool) -> int:
    head = fetch_pr_head(repo)
    print(f"PR355_FETCHED_HEAD={head}")
    print("PRIMARY_WORKTREE_SWITCHED=NO")
    print("PRIMARY_WORKTREE_RESET=NO")
    print("PRIMARY_WORKTREE_CLEAN=NO")
    print("PRIMARY_WORKTREE_STASH=NO")

    add_detached_worktree(repo, worktree, head)
    print(f"ISOLATED_WORKTREE={worktree}")

    diagnostic = (
        worktree
        / "tools"
        / "phase7_holdout_runner"
        / "live_mapping_key_diagnostic.py"
    )
    if not diagnostic.is_file():
        if not keep_worktree:
            remove_worktree(repo, worktree)
        raise BootstrapError(f"PR355 diagnostic script missing: {diagnostic}")

    try:
        run = subprocess.run(
            [sys.executable, str(diagnostic), "--repo-root", str(worktree)],
            check=False,
        )
        return_code = int(run.returncode)
    finally:
        if keep_worktree:
            print(f"ISOLATED_WORKTREE_KEPT={worktree}")
        else:
            remove_worktree(repo, worktree)
            print("ISOLATED_WORKTREE_REMOVED=YES")

    return return_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch PR #355 into a detached temporary worktree and run the live mapping-key "
            "diagnostic without switching, resetting, cleaning, or stashing the primary worktree."
        )
    )
    parser.add_argument("--repo", type=Path, default=repo_root())
    parser.add_argument("--worktree", type=Path, default=None)
    parser.add_argument("--keep-worktree", action="store_true")
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
