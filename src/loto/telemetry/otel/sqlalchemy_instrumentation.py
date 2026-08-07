"""SQLAlchemy engine tracing without retaining SQL statements or parameters."""
from __future__ import annotations

import re
from threading import Lock
from weakref import WeakKeyDictionary

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from loto.telemetry.otel.tracing import TracingRuntime

_OPERATION_RE = re.compile(r"^\s*([A-Za-z]+)")
_INSTRUMENTED: WeakKeyDictionary[object, tuple[object, object, object]] = WeakKeyDictionary()
_LOCK = Lock()


def _operation(statement: object) -> str:
    match = _OPERATION_RE.match(str(statement))
    return "UNKNOWN" if match is None else match.group(1).upper()[:32]


def instrument_sqlalchemy_engine(engine: object, runtime: TracingRuntime) -> bool:
    """Attach listeners once; the SQL statement and parameters are never span attributes."""

    if not runtime.config.instrument_sqlalchemy or not runtime.is_active:
        return False
    from sqlalchemy import event

    with _LOCK:
        if engine in _INSTRUMENTED:
            return False

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            span = runtime.tracer.start_span(
                "loto.db.query",
                kind=SpanKind.CLIENT,
                attributes={
                    "db.system.name": engine.dialect.name,
                    "db.operation.name": _operation(statement),
                },
            )
            token = otel_context.attach(trace.set_span_in_context(span))
            conn.info.setdefault("_loto_otel_span_stack", []).append((span, token))

        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            stack = conn.info.get("_loto_otel_span_stack", [])
            if not stack:
                return
            span, token = stack.pop()
            otel_context.detach(token)
            span.set_status(Status(StatusCode.OK))
            span.end()

        def handle_error(exception_context):
            conn = exception_context.connection
            if conn is None:
                return
            stack = conn.info.get("_loto_otel_span_stack", [])
            if not stack:
                return
            span, token = stack.pop()
            otel_context.detach(token)
            exc = exception_context.original_exception
            span.set_attribute("error.type", type(exc).__name__[:256])
            span.set_status(Status(StatusCode.ERROR))
            span.end()

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        event.listen(engine, "after_cursor_execute", after_cursor_execute)
        event.listen(engine, "handle_error", handle_error)
        _INSTRUMENTED[engine] = (before_cursor_execute, after_cursor_execute, handle_error)
        return True


def uninstrument_sqlalchemy_engine(engine: object) -> bool:
    from sqlalchemy import event

    with _LOCK:
        listeners = _INSTRUMENTED.pop(engine, None)
        if listeners is None:
            return False
        event.remove(engine, "before_cursor_execute", listeners[0])
        event.remove(engine, "after_cursor_execute", listeners[1])
        event.remove(engine, "handle_error", listeners[2])
        return True
