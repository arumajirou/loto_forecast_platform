from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from loto.tirex2_campaign.lock_review import LockReviewError, validate_installed_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the reviewed TiRex-2 runtime lane")
    parser.add_argument(
        "--environment",
        type=Path,
        default=REPOSITORY_ROOT / "environments" / "tirex2-supported-py312",
    )
    parser.add_argument("--runtime-lane", default="tirex2-supported-py312")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = validate_installed_review(
            environment_path=args.environment.resolve(strict=True),
            runtime_lane=args.runtime_lane,
        )
    except (LockReviewError, FileNotFoundError) as exc:
        result = {
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
