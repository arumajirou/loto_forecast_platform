"""Field-level evaluation protocol comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DifferenceSeverity(StrEnum):
    """Severity of one protocol difference."""

    RESULT_AFFECTING = "RESULT_AFFECTING"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"


@dataclass(frozen=True, slots=True)
class ProtocolDifference:
    """One field-level protocol difference."""

    path: str
    left: Any
    right: Any
    severity: DifferenceSeverity

    def to_dict(self) -> dict[str, Any]:
        """Return the required JSON shape."""

        return {
            "path": self.path,
            "left": self.left,
            "right": self.right,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class ProtocolDiff:
    """Comparison result for two protocols."""

    comparable: bool
    left_hash: str
    right_hash: str
    differences: tuple[ProtocolDifference, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the required JSON shape."""

        return {
            "comparable": self.comparable,
            "left_hash": self.left_hash,
            "right_hash": self.right_hash,
            "differences": [item.to_dict() for item in self.differences],
        }


class ProtocolComparisonRefused(RuntimeError):
    """Raised when any result-affecting protocol difference exists."""

    def __init__(self, diff: ProtocolDiff) -> None:
        paths = ", ".join(item.path for item in diff.differences[:8])
        super().__init__(f"protocol comparison refused; differences={paths}")
        self.diff = diff


def _walk(left: Any, right: Any, path: str = "") -> list[ProtocolDifference]:
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[ProtocolDifference] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else key
            differences.extend(_walk(left.get(key), right.get(key), child))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        for index in range(max(len(left), len(right))):
            child = f"{path}[{index}]"
            left_value = left[index] if index < len(left) else None
            right_value = right[index] if index < len(right) else None
            differences.extend(_walk(left_value, right_value, child))
        return differences
    if left == right:
        return []
    severity = (
        DifferenceSeverity.SCHEMA_INCOMPATIBLE
        if path == "schema_version"
        else DifferenceSeverity.RESULT_AFFECTING
    )
    return [ProtocolDifference(path, left, right, severity)]


def build_protocol_diff(
    left_payload: dict[str, Any],
    right_payload: dict[str, Any],
    *,
    left_hash: str,
    right_hash: str,
) -> ProtocolDiff:
    """Build a deterministic field-level diff."""

    differences = tuple(_walk(left_payload, right_payload))
    if not differences and left_hash != right_hash:
        differences = (
            ProtocolDifference(
                path="$hash",
                left=left_hash,
                right=right_hash,
                severity=DifferenceSeverity.RESULT_AFFECTING,
            ),
        )
    return ProtocolDiff(
        comparable=not differences and left_hash == right_hash,
        left_hash=left_hash,
        right_hash=right_hash,
        differences=differences,
    )


def assert_protocol_diff_comparable(diff: ProtocolDiff) -> None:
    """Reject comparison when any difference exists."""

    if not diff.comparable:
        raise ProtocolComparisonRefused(diff)
