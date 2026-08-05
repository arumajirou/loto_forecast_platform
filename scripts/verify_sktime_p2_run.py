from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from loto.sktime_campaign.benchmark import ValidationBenchmarkRequest
from loto.sktime_campaign.benchmark_artifacts import (
    BenchmarkVerificationError,
    verify_validation_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a formal sktime P2 run.")
    parser.add_argument("--request", required=True, help="Original request JSON")
    parser.add_argument("--run", required=True, help="P2 output directory")
    parser.add_argument("--allow-partial", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        request_payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
        request = ValidationBenchmarkRequest.model_validate(request_payload)
        report = verify_validation_benchmark(
            Path(args.run),
            request,
            formal=not args.allow_partial,
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValidationError,
        BenchmarkVerificationError,
    ) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
