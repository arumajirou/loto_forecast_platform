#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath

ALLOWED_EXACT = {
    ".mcp.json.example",
    "CLAUDE.md",
    "CLAUDE.harness.md",
    "deploy/harness-stack.compose.yml",
    "pyproject.toml",
    "uv.lock",
}
ALLOWED_PREFIXES = (
    "artifacts/harness/",
    "configs/harness/",
    "deploy/grafana/",
    "deploy/prometheus/",
    "deploy/systemd/user/loto-harness-",
    "docs/harness/",
    "scripts/harness/",
    "src/loto/harness/",
    "tests/harness/",
)


def _git_paths(root: Path) -> set[str]:
    commands = [
        ["git", "diff", "--name-only", "-z"],
        ["git", "diff", "--cached", "--name-only", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        ["git", "ls-files", "--deleted", "-z"],
    ]
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"command failed ({result.returncode}): {' '.join(command)}\n"
                f"{result.stderr.decode(errors='replace')}"
            )
        for raw in result.stdout.split(b"\0"):
            if raw:
                paths.add(raw.decode("utf-8", errors="surrogateescape"))
    return paths


def is_allowed(path: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    if normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
        return False
    return normalized in ALLOWED_EXACT or any(
        normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject changes outside the harness overlay scope")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if (
        not (root / ".git").exists()
        and subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        != 0
    ):
        raise SystemExit(f"not a git worktree: {root}")

    paths = sorted(_git_paths(root))
    blocked = [path for path in paths if not is_allowed(path)]
    for path in paths:
        print(f"{'BLOCKED' if path in blocked else 'ALLOWED'}\t{path}")
    if blocked:
        print(f"HARNESS_SCOPE=FAILED blocked_count={len(blocked)}")
        return 20
    print(f"HARNESS_SCOPE=VERIFIED changed_count={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
