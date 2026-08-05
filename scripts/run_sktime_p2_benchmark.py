from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from loto.sktime_campaign.benchmark import ValidationBenchmarkRequest
from loto.sktime_campaign.benchmark_artifacts import persist_validation_benchmark


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated sktime chronological Validation benchmark."
    )
    parser.add_argument("--request", required=True, help="Benchmark request JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
        request = ValidationBenchmarkRequest.model_validate(payload)
        response = persist_validation_benchmark(request)
    except (OSError, json.JSONDecodeError, ValidationError, RuntimeError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
