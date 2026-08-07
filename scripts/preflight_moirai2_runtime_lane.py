from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.runtime_campaign import write_sha256_manifest  # noqa: E402
from loto.moirai2_campaign.runtime_preflight import (  # noqa: E402
    run_frozen_probe,
    validate_lane_files,
)

RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed preflight for an isolated Moirai 2.0 runtime lane"
    )
    parser.add_argument("--runtime-lane", required=True, choices=sorted(RUNTIME_LANES))
    parser.add_argument("--device", required=True, choices=("cpu", "cuda"))
    parser.add_argument("--snapshot-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        lane_evidence = validate_lane_files(
            RUNTIME_LANES[arguments.runtime_lane],
            arguments.snapshot_path,
            runtime_lane=arguments.runtime_lane,
        )
        probe = run_frozen_probe(
            environment_path=RUNTIME_LANES[arguments.runtime_lane],
            requested_device=arguments.device,
            timeout_seconds=arguments.timeout_seconds,
        )
        report = {
            "status": "PASS",
            "phase": "P8_RUNTIME_PREFLIGHT",
            "runtime_lane": arguments.runtime_lane,
            "requested_device": arguments.device,
            "lane_evidence": lane_evidence,
            "probe": probe,
        }
    except Exception as exc:
        report = {
            "status": "FAILED",
            "phase": "P8_RUNTIME_PREFLIGHT",
            "runtime_lane": arguments.runtime_lane,
            "requested_device": arguments.device,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    _write_json(arguments.output_dir / "preflight.json", report)
    write_sha256_manifest(arguments.output_dir, arguments.output_dir / "SHA256SUMS")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
