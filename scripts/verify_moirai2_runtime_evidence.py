from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.runtime_evidence_gate import (  # noqa: E402
    RuntimeEvidenceGateError,
    verify_runtime_evidence_pair,
    write_sha256_manifest,
)


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Independently verify supported and CUDA Moirai 2.0 runtime campaign evidence")
    )
    parser.add_argument("--supported-campaign-dir", required=True, type=Path)
    parser.add_argument("--cuda-campaign-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-source-commit")
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        report = verify_runtime_evidence_pair(
            supported_campaign_dir=arguments.supported_campaign_dir,
            cuda_campaign_dir=arguments.cuda_campaign_dir,
            expected_source_commit=arguments.expected_source_commit,
        )
    except Exception as exc:
        report = {
            "schema_version": "moirai2-p8c-runtime-evidence-gate-v1",
            "status": "FAILED",
            "phase": "P8C_RUNTIME_EVIDENCE_GATE",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "p9_oof_gate_open": False,
            "accuracy_claimed": False,
            "oof_executed": False,
            "holdout_executed": False,
            "prospective_executed": False,
        }
    _write_json(arguments.output_dir / "P8C_RUNTIME_EVIDENCE_REPORT.json", report)
    _write_json(
        arguments.output_dir / "ARTIFACT_MANIFEST.json",
        {
            "schema_version": "moirai2-p8c-artifact-manifest-v1",
            "files": ["P8C_RUNTIME_EVIDENCE_REPORT.json"],
            "file_count": 1,
        },
    )
    write_sha256_manifest(arguments.output_dir, arguments.output_dir / "SHA256SUMS")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
