"""Evaluation-protocol fingerprinting.

Constitution principle V: comparing metrics produced under different evaluation conditions
is a hard error. This module defines the canonical fingerprint (``protocol_hash``) and the
guard that refuses to rank across mismatched fingerprints.

The hash covers *only* fields that change what a metric means. Cosmetic fields (run id,
timestamps, output paths, worker counts) are deliberately excluded so that two honest reruns
of the same protocol agree. Conversely ``horizon`` and ``tau`` are included, because a model
evaluated at ``horizon=1`` is not comparable to one evaluated at ``horizon=4`` no matter how
similar the numbers look.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = [
    "ProtocolSpec",
    "ProtocolMismatch",
    "protocol_hash",
    "assert_comparable",
    "group_by_protocol",
]

#: Fields that participate in the fingerprint, in canonical order.
HASHED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "game",
    "family",
    "positions",
    "universe_size",
    "target_mode",
    "horizon",
    "tau",
    "metric_set",
    "data_version",
    "development_rows",
    "holdout_rows",
    "folds",
    "test_size",
    "gap",
    "expanding",
    "min_train_size",
    "seeds",
    "objective_primary",
    "objective_weights",
    "feature_windows",
    "exponential_halflives",
)


class ProtocolMismatch(RuntimeError):
    """Raised when metrics from different protocols would be compared."""

    def __init__(self, expected: str, found: dict[str, list[str]]) -> None:
        detail = "; ".join(f"{h[:12]}…={sorted(v)}" for h, v in sorted(found.items()))
        super().__init__(
            f"cross-protocol comparison refused: expected {expected[:12]}…, found {detail}"
        )
        self.expected = expected
        self.found = found


@dataclass(frozen=True)
class ProtocolSpec:
    """The evaluation conditions under which a metric is meaningful."""

    game: str
    family: str
    positions: int
    universe_size: int
    target_mode: str
    horizon: int
    data_version: str
    development_rows: int
    holdout_rows: int
    folds: int
    test_size: int
    min_train_size: int
    objective_primary: str
    schema_version: str = "3.0.0"
    tau: int = 1
    gap: int = 0
    expanding: bool = True
    seeds: tuple[int, ...] = (42,)
    metric_set: tuple[str, ...] = ()
    objective_weights: dict[str, float] = field(default_factory=dict)
    feature_windows: tuple[int, ...] = ()
    exponential_halflives: tuple[float, ...] = ()

    def canonical(self) -> dict[str, Any]:
        """Deterministic, JSON-serialisable projection onto :data:`HASHED_FIELDS`."""
        raw = asdict(self)
        out: dict[str, Any] = {}
        for key in HASHED_FIELDS:
            value = raw.get(key)
            if isinstance(value, tuple):
                value = list(value)
            if isinstance(value, dict):
                value = {k: round(float(v), 12) for k, v in sorted(value.items())}
            if isinstance(value, float):
                value = round(value, 12)
            out[key] = value
        return out

    @property
    def hash(self) -> str:
        return protocol_hash(self.canonical())

    def summary(self) -> dict[str, Any]:
        return {"protocol_hash": self.hash, "protocol": self.canonical()}


def protocol_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON encoding of ``payload``.

    ``sort_keys`` plus ``separators`` makes the encoding independent of insertion order and
    of whitespace, so the hash is stable across Python versions and platforms.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def group_by_protocol(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Map ``protocol_hash`` -> model ids present under it."""
    groups: dict[str, list[str]] = {}
    for row in records:
        key = str(row.get("protocol_hash", ""))
        groups.setdefault(key, []).append(str(row.get("model_id", "<unknown>")))
    return groups


def assert_comparable(records: list[dict[str, Any]], expected: str | None = None) -> str:
    """Return the single shared ``protocol_hash``, or raise :class:`ProtocolMismatch`.

    An empty record list is comparable by definition and returns ``expected`` or ``""``.
    A missing or empty ``protocol_hash`` is treated as a distinct (unknown) protocol rather
    than being silently accepted -- an unlabelled metric is exactly the failure mode this
    guard exists to catch.
    """
    if not records:
        return expected or ""
    groups = group_by_protocol(records)
    if expected is None:
        if len(groups) == 1:
            return next(iter(groups))
        raise ProtocolMismatch(expected="<single>", found=groups)
    if set(groups) != {expected}:
        raise ProtocolMismatch(expected=expected, found=groups)
    return expected
