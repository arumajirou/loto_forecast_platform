from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .calibration_contracts import CalibrationResult
from .evaluation_artifacts import _sha256_file


def persist_calibration_result(
    result: CalibrationResult,
    output_dir: str | Path,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output directory is not empty: {root}")
    if root.exists():
        root.rmdir()
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent))
    try:
        tables = {
            "CHRONOS2_CALIBRATION_SPLITS": result.split_assignments,
            "CHRONOS2_CALIBRATION_PARAMETERS": result.parameters,
            "CHRONOS2_CALIBRATED_PREDICTIONS": result.predictions,
            "CHRONOS2_CALIBRATION_METRICS": result.metrics,
            "CHRONOS2_CALIBRATION_POSITION_METRICS": result.position_metrics,
            "CHRONOS2_CALIBRATION_SEED_SUMMARY": result.seed_summary,
            "CHRONOS2_CALIBRATION_COMPARISON": result.comparison,
        }
        artifacts: dict[str, str] = {}
        parquet_status = "PASS"
        for name, table in tables.items():
            csv_path = staging / f"{name}.csv"
            table.to_csv(csv_path, index=False)
            artifacts[f"{name.lower()}_csv"] = csv_path.name
            parquet_path = staging / f"{name}.parquet"
            try:
                table.to_parquet(parquet_path, index=False)
                artifacts[f"{name.lower()}_parquet"] = parquet_path.name
            except ImportError:
                parquet_status = "NOT_AVAILABLE"

        report = dict(result.report)
        report["parquet_status"] = parquet_status
        report_path = staging / "CHRONOS2_CALIBRATION_REPORT.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts["report"] = report_path.name

        manifest_path = staging / "ARTIFACT_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": report["run_id"],
                    "phase": "P8",
                    "status": report["status"],
                    "artifacts": artifacts,
                    "holdout_opened": False,
                    "prospective_opened": False,
                    "automatic_promotion": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        files = sorted(path for path in staging.iterdir() if path.is_file())
        sums_path = staging / "SHA256SUMS"
        sums_path.write_text(
            "\n".join(f"{_sha256_file(path)}  {path.name}" for path in files) + "\n",
            encoding="utf-8",
        )
        staging.replace(root)
        return {
            "output_dir": str(root),
            "report": report,
            "artifacts": artifacts,
            "manifest": str(root / manifest_path.name),
            "sha256sums": str(root / sums_path.name),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
