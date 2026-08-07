from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .evaluation_contracts import EvaluationResult


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def persist_oof_result(result: EvaluationResult, output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output directory is not empty: {root}")
    if root.exists():
        root.rmdir()
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent)
    )
    try:
        tables = {
            "CHRONOS2_OOF_FOLDS": result.folds,
            "CHRONOS2_OOF_PREDICTIONS": result.predictions,
            "CHRONOS2_OOF_METRICS": result.metrics,
            "CHRONOS2_POSITION_METRICS": result.position_metrics,
            "CHRONOS2_SEED_SUMMARY": result.seed_summary,
            "CHRONOS2_BASELINE_COMPARISON": result.baseline_comparison,
        }
        artifacts: dict[str, Any] = {}
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
        report_path = staging / "CHRONOS2_OOF_REPORT.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts["report"] = report_path.name

        manifest_path = staging / "ARTIFACT_MANIFEST.json"
        manifest_payload = {
            "schema_version": 1,
            "run_id": report["run_id"],
            "status": report["status"],
            "artifacts": artifacts,
        }
        manifest_path.write_text(
            json.dumps(
                manifest_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        files = sorted(path for path in staging.iterdir() if path.is_file())
        sums_path = staging / "SHA256SUMS"
        lines = [f"{_sha256_file(path)}  {path.name}" for path in files]
        sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
