from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .runtime_lane_admission import write_admission_artifacts
from .runtime_lane_admission_hardening import inspect_target_host_archive
from .runtime_lane_end_to_end import EndToEndResult, resolve_git_context
from .runtime_lane_end_to_end import (
    run_end_to_end_certification as _run_end_to_end_certification,
)


def run_end_to_end_certification(
    repo_root: Path,
    output_root: Path,
    *,
    admission_inspector: Callable[..., dict[str, Any]] | None = None,
    admission_writer: Callable[..., dict[str, Path]] | None = None,
    **kwargs: Any,
) -> EndToEndResult:
    """Run the base gate with hardened point/CPU admission defaults."""

    inspector = inspect_target_host_archive if admission_inspector is None else admission_inspector
    writer = write_admission_artifacts if admission_writer is None else admission_writer
    return _run_end_to_end_certification(
        repo_root,
        output_root,
        admission_inspector=inspector,
        admission_writer=writer,
        **kwargs,
    )


__all__ = [
    "EndToEndResult",
    "resolve_git_context",
    "run_end_to_end_certification",
]
