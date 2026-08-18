from __future__ import annotations

import argparse
import os
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from pr355_live_mapping_bootstrap import fetch_pr_head, git_show_bytes, repo_root

PR_FILES: Final = (
    "pyproject.toml",
    "src/loto/evaluation/semantic_config.py",
    "tests/evaluation/test_semantic_config.py",
    "tools/phase7_holdout_runner/derive_canonical_runner.py",
    "tests/test_phase7_holdout_runner_derivation.py",
    "tools/phase7_holdout_runner/frozen_config_forensics.py",
    "tests/test_phase7_frozen_config_forensics.py",
    "tools/phase7_holdout_runner/live_mapping_key_diagnostic.py",
    "tests/test_phase7_live_mapping_key_diagnostic.py",
    "tools/phase7_holdout_runner/DERIVATION_CONTRACT.json",
)

EXPECTED_CRITICAL_BLOBS: Final = {
    "src/loto/evaluation/semantic_config.py": "257d4d4a88e56f6070200a67fd86b2beca73a3c1",
    "tools/phase7_holdout_runner/derive_canonical_runner.py": "efa988d671cb31820d4a4292498dd034c85ce481",
}

PYTHON_FILES: Final = tuple(path for path in PR_FILES if path.endswith(".py"))
TEST_FILES: Final = tuple(path for path in PR_FILES if path.startswith("tests/") and path.endswith(".py"))
RUFF_FILES: Final = PYTHON_FILES


class VerifyBootstrapError(RuntimeError):
    """Raised when exact-head focused verification cannot be proven safe."""


def git_blob_sha1(data: bytes) -> str:
    import hashlib

    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def default_output_root() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-pr355-exact-verify-{stamp}"


def materialize(repo: Path, head: str, root: Path) -> None:
    if root.exists():
        raise VerifyBootstrapError(f"output root already exists: {root}")
    root.mkdir(parents=True, exist_ok=False)
    try:
        for relative in PR_FILES:
            data = git_show_bytes(repo, head, relative)
            expected = EXPECTED_CRITICAL_BLOBS.get(relative)
            actual = git_blob_sha1(data)
            if expected is not None and actual != expected:
                raise VerifyBootstrapError(
                    f"PR #355 critical blob drift: {relative} "
                    f"expected={expected} actual={actual}"
                )
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            if expected is not None:
                print(f"PR355_CRITICAL_BLOB=PASS path={relative} blob={actual}")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def find_uv() -> str:
    uv = shutil.which("uv") or shutil.which("uv.exe")
    if uv is None:
        raise VerifyBootstrapError("uv executable not found on PATH")
    return uv


def run_checked(command: list[str], *, cwd: Path, env: dict[str, str], label: str) -> None:
    run = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if run.stdout:
        print(run.stdout, end="" if run.stdout.endswith("\n") else "\n")
    if run.stderr:
        print(run.stderr, end="" if run.stderr.endswith("\n") else "\n")
    if run.returncode != 0:
        raise VerifyBootstrapError(f"{label} failed rc={run.returncode}")


def run_verify(*, repo: Path, output_root: Path, keep: bool) -> int:
    head = fetch_pr_head(repo)
    print(f"PR355_FETCHED_HEAD={head}")
    print("PRIMARY_WORKTREE_SWITCHED=NO")
    print("PRIMARY_WORKTREE_RESET=NO")
    print("PRIMARY_WORKTREE_CLEAN=NO")
    print("PRIMARY_WORKTREE_STASH=NO")
    print("WINDOWS_INVALID_PATH_CHECKOUT_AVOIDED=YES")

    materialize(repo, head, output_root)
    print(f"ISOLATED_MATERIALIZED_ROOT={output_root}")
    print(f"SELECTIVE_FILE_COUNT={len(PR_FILES)}")

    try:
        for relative in PYTHON_FILES:
            py_compile.compile(str(output_root / relative), doraise=True)
        print("PY_COMPILE=PASS")

        uv = find_uv()
        env = dict(os.environ)
        src = str(output_root / "src")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing

        run_checked(
            [uv, "tool", "run", "--from", "pytest>=8,<9", "pytest", "-q", *TEST_FILES],
            cwd=output_root,
            env=env,
            label="focused pytest",
        )
        print("FOCUSED_PYTEST=PASS")

        config = str(output_root / "pyproject.toml")
        run_checked(
            [uv, "tool", "run", "--from", "ruff>=0.16.3", "ruff", "format", "--check", "--config", config, *RUFF_FILES],
            cwd=output_root,
            env=env,
            label="Ruff format",
        )
        print("RUFF_FORMAT=PASS")

        run_checked(
            [uv, "tool", "run", "--from", "ruff>=0.16.3", "ruff", "check", "--config", config, *RUFF_FILES],
            cwd=output_root,
            env=env,
            label="Ruff lint",
        )
        print("RUFF_LINT=PASS")

        print("STATUS=PASS")
        return 0
    finally:
        if keep:
            print(f"ISOLATED_MATERIALIZED_ROOT_KEPT={output_root}")
        else:
            shutil.rmtree(output_root, ignore_errors=True)
            print("ISOLATED_MATERIALIZED_ROOT_REMOVED=YES")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the current PR #355 head, selectively materialize only focused scientific "
            "files/tests, and run py_compile, focused pytest, Ruff format and Ruff lint without "
            "checking out Windows-invalid historical paths."
        )
    )
    parser.add_argument("--repo", type=Path, default=repo_root())
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root or default_output_root()
    return run_verify(
        repo=args.repo.resolve(),
        output_root=output_root.resolve(),
        keep=args.keep,
    )


if __name__ == "__main__":
    raise SystemExit(main())
