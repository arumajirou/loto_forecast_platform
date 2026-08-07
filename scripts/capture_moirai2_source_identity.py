from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.runtime_source_identity import (  # noqa: E402
    capture_source_identity,
)

PRINCIPAL_PATHS = (
    "scripts/run_moirai2_provider.py",
    "scripts/certify_moirai2_runtime.py",
    "scripts/run_moirai2_runtime_campaign.py",
    "src/loto/adapters/moirai2/contracts.py",
    "src/loto/moirai2_campaign/covariates.py",
    "src/loto/moirai2_campaign/runtime_campaign.py",
    "src/loto/moirai2_campaign/runtime_certification.py",
    "src/loto/moirai2_campaign/runtime_evidence_gate.py",
    "src/loto/moirai2_campaign/runtime_preflight.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture clean-tree source identity for Moirai runtime evidence"
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    evidence = capture_source_identity(
        repo_root=ROOT,
        principal_paths=PRINCIPAL_PATHS,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_name(arguments.output.name + ".tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
