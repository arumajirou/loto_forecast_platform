from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from loto.tirex2_campaign.lock_review import LockReviewError, install_reviewed_lock


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a reviewed TiRex-2 lock")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument(
        "--environment",
        type=Path,
        default=REPOSITORY_ROOT / "environments" / "tirex2-supported-py312",
    )
    parser.add_argument("--runtime-lane", default="tirex2-supported-py312")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--expected-candidate-lock-sha256", required=True)
    parser.add_argument("--expected-current-lock-sha256")
    parser.add_argument("--approval-token")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = install_reviewed_lock(
            candidate_path=args.candidate.resolve(strict=True),
            environment_path=args.environment.resolve(strict=True),
            runtime_lane=args.runtime_lane,
            reviewer=args.reviewer,
            reviewed_at=args.reviewed_at,
            expected_candidate_lock_sha256=args.expected_candidate_lock_sha256,
            apply=args.apply,
            approval_token=args.approval_token,
            expected_current_lock_sha256=args.expected_current_lock_sha256,
        )
    except (LockReviewError, FileNotFoundError) as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_type": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
