from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DriftSummary:
    rows_reference: int
    rows_current: int
    drifted_columns: tuple[str, ...]
    available: bool


def build_drift_summary(reference: pd.DataFrame, current: pd.DataFrame) -> DriftSummary:
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except ImportError:
        return DriftSummary(len(reference), len(current), (), False)
    report = Report([DataDriftPreset()])
    result = report.run(reference_data=reference, current_data=current)
    payload = result.dict()
    drifted = tuple(sorted(str(item.get("column_name")) for item in payload.get("metrics", []) if item.get("value", {}).get("drift_detected") is True))
    return DriftSummary(len(reference), len(current), drifted, True)
