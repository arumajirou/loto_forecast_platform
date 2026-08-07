from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from pydantic import BaseModel, Field

from ..errors import EngineUnavailable
from ..security import ensure_allowed_path


class ClaudeCodeConfig(BaseModel):
    executable: str = "claude"
    model: str = "sonnet"
    max_turns: int = Field(default=12, ge=1, le=100)
    timeout_seconds: int = Field(default=3600, ge=1)
    allowed_tools: list[str] = Field(
        default_factory=lambda: [
            "Read",
            "Grep",
            "Glob",
            "Edit",
            "Write",
            "Bash(git status *)",
            "Bash(git diff *)",
            "Bash(uv run pytest *)",
            "Bash(uv run ruff *)",
            "Bash(uv run mypy *)",
        ]
    )
    disallowed_tools: list[str] = Field(
        default_factory=lambda: [
            "Bash(git push *)",
            "Bash(git reset *)",
            "Bash(git clean *)",
            "Bash(rm *)",
            "Bash(sudo *)",
        ]
    )


class ClaudeCodeRunner:
    def __init__(self, config: ClaudeCodeConfig, allowed_roots: list[str]) -> None:
        self.config = config
        self.allowed_roots = allowed_roots

    def command(self, prompt: str, *, read_only: bool = False) -> list[str]:
        executable = shutil.which(self.config.executable) or self.config.executable
        command = [
            executable,
            "-p",
            prompt,
            "--model",
            self.config.model,
            "--max-turns",
            str(self.config.max_turns),
            "--output-format",
            "json",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "Read,Grep,Glob,Bash" if read_only else "Read,Grep,Glob,Edit,Write,Bash",
            "--allowedTools",
        ]
        tools = [
            tool
            for tool in self.config.allowed_tools
            if not read_only or tool not in {"Edit", "Write"}
        ]
        command.extend(tools)
        command.append("--disallowedTools")
        blocked = list(self.config.disallowed_tools)
        if read_only:
            blocked.extend(["Edit", "Write"])
        command.extend(blocked)
        return command

    async def run(self, prompt: str, *, cwd: str, read_only: bool = False) -> dict[str, Any]:
        worktree = ensure_allowed_path(cwd, self.allowed_roots)
        if shutil.which(self.config.executable) is None:
            raise EngineUnavailable(f"Claude Code executable not found: {self.config.executable}")
        process = await asyncio.create_subprocess_exec(
            *self.command(prompt, read_only=read_only),
            cwd=worktree,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            except TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
        text = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")
        payload: dict[str, Any]
        try:
            parsed = json.loads(text)
            payload = parsed if isinstance(parsed, dict) else {"result": parsed}
        except json.JSONDecodeError:
            payload = {"raw_output": text}
        payload.update(
            {
                "exit_code": 124 if timed_out else int(process.returncode or 0),
                "timed_out": timed_out,
                "stderr": error,
                "cwd": str(worktree),
            }
        )
        return payload
