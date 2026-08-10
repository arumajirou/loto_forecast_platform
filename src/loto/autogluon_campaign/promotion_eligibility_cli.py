from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from loto.autogluon_campaign.holdout_prospective import HoldoutProspectiveError
from loto.autogluon_campaign.promotion_eligibility import (
    PromotionPolicy,
    PromotionPolicyV2,
    create_promotion_eligibility,
    promotion_policy_from_payload,
    verify_promotion_eligibility,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or verify AutoGluon P17 promotion eligibility evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--holdout-score", type=Path, required=True)
    create.add_argument(
        "--prospective-score",
        type=Path,
        action="append",
        required=True,
    )
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--policy", type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    return parser


def _load_policy(path: Path | None) -> PromotionPolicy | PromotionPolicyV2:
    if path is None:
        return PromotionPolicy()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("promotion policy must be a JSON object")
    return promotion_policy_from_payload(payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_promotion_eligibility(
                holdout_score_dir=args.holdout_score,
                prospective_score_dirs=args.prospective_score,
                output_dir=args.output,
                policy=_load_policy(args.policy),
                run_id=args.run_id,
            )
            payload = {
                "status": result.status,
                "decision": result.decision,
                "reason_code": result.reason_code,
                "output_dir": result.output_dir,
                "decision_path": result.decision_path,
            }
            print(json.dumps(payload, sort_keys=True))
            return 0 if result.decision == "ELIGIBLE_FOR_HUMAN_APPROVAL" else 2

        verified = verify_promotion_eligibility(args.run)
        print(json.dumps(verified, sort_keys=True))
        return 0 if verified["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL" else 2
    except (
        HoldoutProspectiveError,
        ValidationError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_code": str(code),
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
