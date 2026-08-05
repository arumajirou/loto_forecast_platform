from pathlib import Path

import pytest

from loto.harness.agents.claude_code import ClaudeCodeConfig, ClaudeCodeRunner
from loto.harness.errors import UnsafeOperation


def test_claude_command_has_bounded_permissions(tmp_path: Path) -> None:
    runner = ClaudeCodeRunner(ClaudeCodeConfig(), [str(tmp_path)])
    command = runner.command("review", read_only=True)
    assert Path(command[0]).name == "claude"
    assert command[1] == "-p"
    assert command[2] == "review"
    assert "--max-turns" in command
    assert command[command.index("--tools") + 1] == "Read,Grep,Glob,Bash"
    assert "--strict-mcp-config" in command
    assert "--no-session-persistence" in command
    assert "Edit" in command[command.index("--disallowedTools") + 1 :]
    assert "Bash(git push *)" in command


def test_claude_runner_rejects_outside_worktree(tmp_path: Path) -> None:
    runner = ClaudeCodeRunner(ClaudeCodeConfig(), [str(tmp_path)])
    with pytest.raises(UnsafeOperation):
        # Validation occurs before executable discovery in a real run.
        import asyncio

        asyncio.run(runner.run("x", cwd="/etc", read_only=True))
