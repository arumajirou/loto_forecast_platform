from __future__ import annotations


class DownstreamCommitError(RuntimeError):
    """Base error for downstream commit preparation and execution."""


class DownstreamCommitPreflightError(DownstreamCommitError):
    """Raised before any downstream side effect when evidence is invalid."""


class DownstreamCommitConflict(DownstreamCommitError):
    """Raised when an existing downstream object conflicts with this commit."""


class DownstreamCommitRetryable(DownstreamCommitError):
    """Raised after journaling a step that can be retried safely."""


__all__ = [
    "DownstreamCommitConflict",
    "DownstreamCommitError",
    "DownstreamCommitPreflightError",
    "DownstreamCommitRetryable",
]
