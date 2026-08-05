from __future__ import annotations

from typing import Any, Callable

from .runtime_lane_end_to_end_hardening import run_end_to_end_certification
from .runtime_lane_remediation import (
    RemediationExecutionResult,
    execute_bounded_remediation as _execute_bounded_remediation,
    verify_triage_evidence,
)


def execute_bounded_remediation(
    *args: Any,
    end_to_end_runner: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> RemediationExecutionResult:
    """Execute bounded retries through the hardened End-to-End entrypoint."""

    runner = (
        run_end_to_end_certification
        if end_to_end_runner is None
        else end_to_end_runner
    )
    return _execute_bounded_remediation(
        *args,
        end_to_end_runner=runner,
        **kwargs,
    )


__all__ = [
    "RemediationExecutionResult",
    "execute_bounded_remediation",
    "verify_triage_evidence",
]
