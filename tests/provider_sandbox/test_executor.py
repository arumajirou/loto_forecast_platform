from __future__ import annotations

import sys

from loto.provider_sandbox import (
    ProcessOutcome,
    SandboxArgvPlan,
    SandboxBackend,
    SandboxProcessRunner,
)


def plan(*arguments: str) -> SandboxArgvPlan:
    return SandboxArgvPlan.create(
        backend=SandboxBackend.NONE,
        argv=(sys.executable, *arguments),
        environment_keys=(),
    )


def test_success_and_nonzero() -> None:
    runner = SandboxProcessRunner()
    success = runner.run(
        plan("-c", "print('ok')"),
        timeout_seconds=2,
        output_limit_bytes=1024,
    )
    assert success.outcome == ProcessOutcome.SUCCEEDED
    failure = runner.run(
        plan("-c", "raise SystemExit(7)"),
        timeout_seconds=2,
        output_limit_bytes=1024,
    )
    assert failure.outcome == ProcessOutcome.NONZERO_EXIT
    assert failure.exit_code == 7


def test_timeout() -> None:
    result = SandboxProcessRunner().run(
        plan("-c", "import time; time.sleep(2)"),
        timeout_seconds=0.05,
        output_limit_bytes=1024,
    )
    assert result.outcome == ProcessOutcome.TIMED_OUT
    assert result.timed_out is True


def test_oversized_output() -> None:
    result = SandboxProcessRunner().run(
        plan("-c", "print('x' * 4096)"),
        timeout_seconds=2,
        output_limit_bytes=128,
    )
    assert result.outcome == ProcessOutcome.OUTPUT_LIMIT_EXCEEDED
    assert result.stdout_size_bytes > 128
