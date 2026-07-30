"""Provenance completeness gate.

The v2.1.0 quality gate returned ``PASS`` with ``issues: []`` on all six games while
``game``, ``game_display_name`` and ``source_url`` were null in 24 of 24 rows. A lineage
platform whose lineage columns are empty has a gate that checks everything except the thing
it exists to protect.

This gate is separate from the value-range gate on purpose: a range violation means the data
is wrong, whereas a provenance violation means the data is *unattributable*. They have
different remediations and must not be collapsed into one boolean.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

__all__ = [
    "REQUIRED_PROVENANCE_COLUMNS",
    "ProvenanceIssue",
    "ProvenanceReport",
    "check_provenance",
]

#: Columns that must be present and fully populated on every normalised frame.
REQUIRED_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "game", "game_display_name", "source_url", "draw_no", "draw_date",
)

#: Columns that must be present, fully populated, and identical across every row.
CONSTANT_PROVENANCE_COLUMNS: tuple[str, ...] = ("game", "game_display_name", "source_url")


@dataclass(frozen=True)
class ProvenanceIssue:
    column: str
    kind: str
    n_affected: int
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "column": self.column,
            "kind": self.kind,
            "n_affected": self.n_affected,
            "detail": self.detail,
        }


@dataclass
class ProvenanceReport:
    rows: int
    issues: list[ProvenanceIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "PASS" if not self.issues else "FAIL"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "rows": self.rows,
            "required_columns": list(REQUIRED_PROVENANCE_COLUMNS),
            "n_issues": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


def check_provenance(
    frame: pd.DataFrame,
    *,
    expected_game: str | None = None,
    expected_source_url: str | None = None,
) -> ProvenanceReport:
    """Verify that every provenance column is present, complete and consistent."""
    report = ProvenanceReport(rows=int(len(frame)))
    if frame.empty:
        report.issues.append(ProvenanceIssue("<frame>", "empty", 0, "no rows to attribute"))
        return report

    for column in REQUIRED_PROVENANCE_COLUMNS:
        if column not in frame.columns:
            report.issues.append(
                ProvenanceIssue(column, "missing_column", len(frame), "column absent from frame")
            )
            continue
        series = frame[column]
        n_null = int(series.isna().sum())
        if n_null:
            report.issues.append(
                ProvenanceIssue(column, "null_values", n_null,
                                f"{n_null}/{len(frame)} rows unattributable")
            )
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            blank = int((series.fillna("").astype(str).str.strip() == "").sum())
            if blank and blank != n_null:
                report.issues.append(
                    ProvenanceIssue(column, "blank_values", blank, "empty-string values present")
                )

    for column in CONSTANT_PROVENANCE_COLUMNS:
        if column not in frame.columns:
            continue
        distinct = frame[column].dropna().unique()
        if len(distinct) > 1:
            report.issues.append(
                ProvenanceIssue(column, "inconsistent", len(distinct),
                                f"expected one value, found {sorted(map(str, distinct))[:5]}")
            )

    if expected_game is not None and "game" in frame.columns:
        wrong = int((frame["game"].dropna().astype(str) != expected_game).sum())
        if wrong:
            report.issues.append(
                ProvenanceIssue("game", "mismatch", wrong, f"expected {expected_game!r}")
            )
    if expected_source_url is not None and "source_url" in frame.columns:
        wrong = int((frame["source_url"].dropna().astype(str) != expected_source_url).sum())
        if wrong:
            report.issues.append(
                ProvenanceIssue("source_url", "mismatch", wrong,
                                f"expected {expected_source_url!r}")
            )
    return report
