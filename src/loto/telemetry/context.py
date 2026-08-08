"""Context-variable based telemetry correlation without global leakage."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    request_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    game_id: str | None = None
    model_id: str | None = None
    fold_id: int | None = None
    seed: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            key: value
            for key, value in {
                "request_id": self.request_id,
                "run_id": self.run_id,
                "trace_id": self.trace_id,
                "span_id": self.span_id,
                "game_id": self.game_id,
                "model_id": self.model_id,
                "fold_id": self.fold_id,
                "seed": self.seed,
            }.items()
            if value is not None
        }


_CURRENT: ContextVar[TelemetryContext] = ContextVar(
    "loto_telemetry_context", default=TelemetryContext()
)


def _validate_context(context: TelemetryContext) -> None:
    for name in ("request_id", "run_id"):
        value = getattr(context, name)
        if value is not None and not _ID_RE.fullmatch(value):
            raise ValueError(f"invalid {name}")
    if context.trace_id is not None and not _TRACE_ID_RE.fullmatch(context.trace_id):
        raise ValueError("invalid trace_id")
    if context.span_id is not None and not _SPAN_ID_RE.fullmatch(context.span_id):
        raise ValueError("invalid span_id")
    if context.fold_id is not None and context.fold_id < 0:
        raise ValueError("fold_id must be >= 0")


def current_telemetry_context() -> TelemetryContext:
    """Return the current immutable correlation context."""

    return _CURRENT.get()


@contextmanager
def bind_telemetry_context(**values: object) -> Iterator[TelemetryContext]:
    """Temporarily merge correlation fields and restore the prior context on exit."""

    unknown = set(values).difference(TelemetryContext.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown telemetry context fields: {sorted(unknown)}")
    next_context = replace(current_telemetry_context(), **values)
    _validate_context(next_context)
    token = _CURRENT.set(next_context)
    try:
        yield next_context
    finally:
        _CURRENT.reset(token)
