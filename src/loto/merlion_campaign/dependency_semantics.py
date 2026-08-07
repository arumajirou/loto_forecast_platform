from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Iterable, Mapping

from loto.merlion_campaign.dependency_gate import (
    _canonical_sha256,
    audit_uv_lock,
)

_CLAUSE_PATTERN = re.compile(
    r"^(~=|==|!=|<=|>=|<|>)(\d+(?:\.\d+){0,2})(\.\*)?$"
)
_BASE_CANDIDATES = {
    (0, 0, 0),
    (2, 0, 0),
    (3, 0, 0),
    (3, 10, 0),
    (3, 11, 0),
    (3, 11, 1),
    (3, 12, 0),
    (4, 0, 0),
    (99, 0, 0),
}


class PythonConstraintError(ValueError):
    """Raised when a Python version constraint cannot be audited safely."""


def _parse_version(value: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in value.split("."))
    if not 1 <= len(parts) <= 3:
        raise PythonConstraintError(f"unsupported Python version: {value}")
    return parts


def _normalize(parts: tuple[int, ...]) -> tuple[int, int, int]:
    return tuple((*parts, 0, 0)[:3])  # type: ignore[return-value]


def _parse_specifier(specifier: object) -> tuple[tuple[str, tuple[int, ...], bool], ...]:
    if not isinstance(specifier, str) or not specifier.strip():
        raise PythonConstraintError("Python constraint is missing")
    clauses: list[tuple[str, tuple[int, ...], bool]] = []
    for raw_clause in specifier.split(","):
        clause = raw_clause.strip().replace(" ", "")
        match = _CLAUSE_PATTERN.fullmatch(clause)
        if match is None:
            raise PythonConstraintError(f"unsupported Python constraint clause: {raw_clause}")
        operator, version_text, wildcard_text = match.groups()
        wildcard = wildcard_text is not None
        if wildcard and operator not in {"==", "!="}:
            raise PythonConstraintError(
                f"wildcard is unsupported for operator {operator}: {raw_clause}"
            )
        clauses.append((operator, _parse_version(version_text), wildcard))
    return tuple(clauses)


def _compatible_upper(parts: tuple[int, ...]) -> tuple[int, int, int]:
    if len(parts) == 1:
        return (parts[0] + 1, 0, 0)
    if len(parts) == 2:
        return (parts[0] + 1, 0, 0)
    return (parts[0], parts[1] + 1, 0)


def _clause_accepts(
    clause: tuple[str, tuple[int, ...], bool],
    version: tuple[int, int, int],
) -> bool:
    operator, parts, wildcard = clause
    normalized = _normalize(parts)
    if wildcard:
        prefix = version[: len(parts)]
        matched = prefix == parts
        return matched if operator == "==" else not matched
    if operator == "==":
        return version == normalized
    if operator == "!=":
        return version != normalized
    if operator == ">=":
        return version >= normalized
    if operator == ">":
        return version > normalized
    if operator == "<=":
        return version <= normalized
    if operator == "<":
        return version < normalized
    if operator == "~=":
        return version >= normalized and version < _compatible_upper(parts)
    raise PythonConstraintError(f"unsupported Python constraint operator: {operator}")


def _accepts(
    clauses: Iterable[tuple[str, tuple[int, ...], bool]],
    version: tuple[int, int, int],
) -> bool:
    return all(_clause_accepts(clause, version) for clause in clauses)


def _neighbor_candidates(
    clauses: Iterable[tuple[str, tuple[int, ...], bool]],
) -> set[tuple[int, int, int]]:
    candidates = set(_BASE_CANDIDATES)
    for operator, parts, wildcard in clauses:
        normalized = _normalize(parts)
        candidates.add(normalized)
        major, minor, patch = normalized
        if patch > 0:
            candidates.add((major, minor, patch - 1))
        candidates.add((major, minor, patch + 1))
        candidates.add((major, minor, 999_999))

        if minor > 0:
            candidates.add((major, minor - 1, 999_999))
        candidates.add((major, minor + 1, 0))

        if major > 0:
            candidates.add((major - 1, 999, 999_999))
        candidates.add((major + 1, 0, 0))

        if wildcard:
            candidates.add((major, minor, 0))
            candidates.add((major, minor, 1))
            candidates.add((major, minor, 999_999))
        if operator == "~=":
            upper = _compatible_upper(parts)
            candidates.add(upper)
            upper_major, upper_minor, upper_patch = upper
            if upper_patch > 0:
                candidates.add((upper_major, upper_minor, upper_patch - 1))
            elif upper_minor > 0:
                candidates.add((upper_major, upper_minor - 1, 999_999))
            elif upper_major > 0:
                candidates.add((upper_major - 1, 999, 999_999))
    return candidates


def python_constraints_equivalent(left: object, right: object) -> bool:
    left_clauses = _parse_specifier(left)
    right_clauses = _parse_specifier(right)
    candidates = _neighbor_candidates((*left_clauses, *right_clauses))
    return all(
        _accepts(left_clauses, version) == _accepts(right_clauses, version)
        for version in candidates
    )


def _requires_python_mismatch_prefix() -> str:
    return "REQUIRES_PYTHON_MISMATCH:"


def audit_uv_lock_semantic(lock_path: Path, pyproject_path: Path) -> dict[str, Any]:
    report = dict(audit_uv_lock(lock_path, pyproject_path))
    project_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_constraint = project_data.get("project", {}).get("requires-python")
    lock_constraint = report.get("requires_python")

    blockers = [str(value) for value in report.get("blockers", [])]
    mismatch = [
        value for value in blockers if value.startswith(_requires_python_mismatch_prefix())
    ]

    equivalent = False
    semantic_error: str | None = None
    try:
        equivalent = python_constraints_equivalent(lock_constraint, project_constraint)
    except PythonConstraintError as exc:
        semantic_error = str(exc)

    if mismatch and equivalent:
        blockers = [value for value in blockers if value not in mismatch]
    elif semantic_error is not None:
        blockers.append(f"REQUIRES_PYTHON_SEMANTIC_AUDIT_INVALID:{semantic_error}")

    report["project_requires_python"] = project_constraint
    report["requires_python_equivalent"] = equivalent
    report["requires_python_semantic_error"] = semantic_error
    report["blockers"] = sorted(set(blockers))
    report["status"] = "PASS" if not blockers else "BLOCKED"
    report.pop("report_sha256", None)
    report["report_sha256"] = _canonical_sha256(report)
    return report
