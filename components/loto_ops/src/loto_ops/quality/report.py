from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from loto_ops.config import AppSettings
from loto_ops.models import TableProfile
from loto_ops.quality.validators import QualityValidator


def write_quality_reports(
    settings: AppSettings, profiles: list[TableProfile], *, run_dir: Path | None = None
) -> dict[str, Path]:
    out_dir = settings.paths.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
    validator = QualityValidator()
    issues = validator.validate_profiles(
        profiles, require_exog=bool(settings.pipeline.get("require_exog", False))
    )
    data = {
        "profiles": [p.__dict__ for p in profiles],
        "issues": [i.__dict__ for i in issues],
    }
    json_path = out_dir / "data_quality_report.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    table_profile_path = out_dir / "table_profile.csv"
    pd.DataFrame([p.__dict__ for p in profiles]).to_csv(
        table_profile_path, index=False, encoding="utf-8"
    )
    html_path = out_dir / "data_quality_report.html"
    html = "<h1>Loto Ops Data Quality Report</h1>"
    html += pd.DataFrame([p.__dict__ for p in profiles]).to_html(index=False)
    if issues:
        html += "<h2>Issues</h2>" + pd.DataFrame([i.__dict__ for i in issues]).to_html(index=False)
    html_path.write_text(html, encoding="utf-8")
    if run_dir:
        (run_dir / "data_quality_report.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {"json": json_path, "csv": table_profile_path, "html": html_path}
