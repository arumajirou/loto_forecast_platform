from __future__ import annotations

import hashlib
import json
from itertools import combinations, product
from typing import Any


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=repr)


def build_pairwise_plan(levels: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Generate a deterministic, explicit pairwise-covering plan.

    It is intentionally conservative: every value combination for every pair is
    emitted while all other factors remain at their baseline. This can be larger
    than IPOG, but coverage is transparent and auditable.
    """
    if not levels:
        return [{}]
    normalized = {key: list(values) for key, values in sorted(levels.items())}
    for key, values in normalized.items():
        if not values:
            raise ValueError(f"factor has no values: {key}")

    baseline = {key: values[0] for key, values in normalized.items()}
    rows: list[dict[str, Any]] = [dict(baseline)]

    # Single-factor coverage.
    for key, values in normalized.items():
        for value in values:
            row = dict(baseline)
            row[key] = value
            rows.append(row)

    # Pairwise coverage.
    for left, right in combinations(normalized, 2):
        for left_value, right_value in product(normalized[left], normalized[right]):
            row = dict(baseline)
            row[left] = left_value
            row[right] = right_value
            rows.append(row)

    # Boundary interaction rows.
    rows.append({key: values[-1] for key, values in normalized.items()})
    rows.append(
        {
            key: values[-1] if index % 2 else values[0]
            for index, (key, values) in enumerate(normalized.items())
        }
    )

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(_canonical(row), row)
    result = list(deduped.values())
    result.sort(key=_canonical)
    return result


def coverage_report(levels: dict[str, list[Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected: set[str] = set()
    covered: set[str] = set()
    keys = sorted(levels)
    for left, right in combinations(keys, 2):
        for left_value, right_value in product(levels[left], levels[right]):
            expected.add(_canonical({left: left_value, right: right_value}))
    for row in rows:
        for left, right in combinations(keys, 2):
            covered.add(_canonical({left: row[left], right: row[right]}))
    missing = sorted(expected - covered)
    return {
        "expected_pairs": len(expected),
        "covered_pairs": len(expected & covered),
        "missing_pairs": missing,
        "coverage_rate": 1.0 if not expected else len(expected & covered) / len(expected),
        "row_count": len(rows),
        "plan_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, ensure_ascii=False, default=repr).encode("utf-8")
        ).hexdigest(),
    }
