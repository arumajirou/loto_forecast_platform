from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from ..errors import UnsafeOperation
from ..security import ensure_allowed_path, sha256_bytes


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def signature(self) -> str:
        payload = f"{self.exit_code}\n{self.stderr[-4000:]}\n{self.stdout[-4000:]}".encode()
        return sha256_bytes(payload)


class SafeCommandRunner:
    def __init__(self, allowed_roots: list[str], default_timeout: int = 300) -> None:
        self.allowed_roots = allowed_roots
        self.default_timeout = default_timeout

    async def run(
        self,
        args: list[str],
        *,
        cwd: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        if not args or not args[0]:
            raise UnsafeOperation("empty command")
        resolved_cwd = ensure_allowed_path(cwd, self.allowed_roots)
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=resolved_cwd,
            env=process_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout or self.default_timeout
            )
        except TimeoutError:
            timed_out = True
            process.terminate()
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=5
                )
            except TimeoutError:
                process.kill()
                stdout_bytes, stderr_bytes = await process.communicate()
        return CommandResult(
            args=tuple(args),
            cwd=str(resolved_cwd),
            exit_code=124 if timed_out else int(process.returncode or 0),
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            timed_out=timed_out,
        )


class GitCheckpointManager:
    def __init__(self, runner: SafeCommandRunner) -> None:
        self.runner = runner

    async def checkpoint(self, worktree: str, artifact_dir: str) -> dict[str, str]:
        artifact_root = ensure_allowed_path(artifact_dir, self.runner.allowed_roots)
        artifact_root.mkdir(parents=True, exist_ok=True)
        head = await self.runner.run(["git", "rev-parse", "HEAD"], cwd=worktree)
        status = await self.runner.run(["git", "status", "--porcelain=v1"], cwd=worktree)
        diff = await self.runner.run(["git", "diff", "--binary"], cwd=worktree)
        staged = await self.runner.run(["git", "diff", "--cached", "--binary"], cwd=worktree)
        if head.exit_code != 0:
            raise UnsafeOperation(f"not a git worktree: {worktree}")
        (artifact_root / "HEAD.txt").write_text(head.stdout, encoding="utf-8")
        (artifact_root / "status.txt").write_text(status.stdout, encoding="utf-8")
        (artifact_root / "working.patch").write_text(diff.stdout, encoding="utf-8")
        (artifact_root / "staged.patch").write_text(staged.stdout, encoding="utf-8")
        return {
            "head": head.stdout.strip(),
            "status_sha256": sha256_bytes(status.stdout.encode()),
            "diff_sha256": sha256_bytes(diff.stdout.encode()),
            "artifact_dir": str(artifact_root),
        }
