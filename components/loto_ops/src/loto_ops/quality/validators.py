from __future__ import annotations

from dataclasses import dataclass

from loto_ops.models import TableProfile


@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str


class QualityValidator:
    def validate_profiles(
        self, profiles: list[TableProfile], *, require_exog: bool = False
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        by_name = {f"{p.schema}.{p.table}": p for p in profiles}
        for name in ["dataset.loto_y_ts", "dataset.loto_hist_feat", "dataset.loto_y_ts_unified"]:
            p = by_name.get(name)
            if p is None or p.rows is None:
                issues.append(ValidationIssue("error", "TABLE_MISSING", f"{name} is missing"))
            elif p.rows == 0:
                issues.append(ValidationIssue("error", "TABLE_EMPTY", f"{name} is empty"))
        exog = by_name.get("exog.loto_y_ts_exog")
        if require_exog and (exog is None or exog.rows is None or exog.rows == 0):
            issues.append(
                ValidationIssue("error", "EXOG_MISSING", "exog.loto_y_ts_exog is required")
            )
        elif exog is None or exog.rows is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    "EXOG_MISSING",
                    "exog.loto_y_ts_exog is missing; unified may be hist-only",
                )
            )
        yts = by_name.get("dataset.loto_y_ts")
        unified = by_name.get("dataset.loto_y_ts_unified")
        if (
            yts
            and unified
            and yts.rows is not None
            and unified.rows is not None
            and yts.rows != unified.rows
        ):
            issues.append(
                ValidationIssue("error", "ROW_MISMATCH", "unified rows must equal loto_y_ts rows")
            )
        return issues
