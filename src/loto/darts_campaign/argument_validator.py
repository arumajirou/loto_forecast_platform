from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from .protocol import ArgumentDecision, ArgumentStatus


def classify_arguments(
    target: Callable[..., Any],
    requested: Mapping[str, Any],
    *,
    strict: bool = True,
) -> tuple[dict[str, Any], list[ArgumentDecision]]:
    """Classify every requested argument without silently deleting any key."""

    signature = inspect.signature(target)
    accepted_names = set(signature.parameters)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    effective: dict[str, Any] = {}
    decisions: list[ArgumentDecision] = []
    rejected: list[str] = []

    for key, value in requested.items():
        if key in accepted_names or accepts_kwargs:
            effective[key] = value
            status = ArgumentStatus.ACCEPTED
            reason = "callable signature accepts argument"
        else:
            status = ArgumentStatus.REJECTED if strict else ArgumentStatus.NOT_APPLICABLE
            reason = "argument is absent from callable signature"
            if strict:
                rejected.append(key)
        decisions.append(
            ArgumentDecision(
                argument=key,
                status=status,
                reason=reason,
                value_repr=repr(value),
            )
        )

    if rejected:
        joined = ", ".join(sorted(rejected))
        raise ValueError(f"rejected arguments for {target}: {joined}")
    return effective, decisions
