#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.chronos2_campaign.provider import execute_request  # noqa: E402
from loto.chronos2_campaign.runtime_matrix import (  # noqa: E402
    RuntimeMatrixConfig,
    default_scenarios,
    persist_runtime_matrix,
    run_runtime_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    config = RuntimeMatrixConfig(
        run_id=f"{request['run_id']}-runtime-matrix",
        scenarios=default_scenarios(),
        runtime_mode="real",
    )
    result = run_runtime_matrix(
        request,
        config,
        lambda payload: execute_request(payload).model_dump(mode="json"),
    )
    artifacts = persist_runtime_matrix(result, args.output)
    print(json.dumps({"status": result.status, "artifacts": artifacts}, indent=2))
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
