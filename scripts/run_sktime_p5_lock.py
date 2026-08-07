from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.prospective import ProspectiveRequest
from loto.sktime_campaign.prospective_artifacts import (
    P4LineageContext,
    persist_prospective_lock,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a pre-actual sktime P5 Prospective shadow lock."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--p4-artifact-sha256", required=True)
    parser.add_argument("--p4-selected-candidate", required=True)
    parser.add_argument("--p4-response-sha256", required=True)
    parser.add_argument("--p4-sha256sums-sha256", required=True)
    parser.add_argument("--p4-aggregates-sha256", required=True)
    parser.add_argument("--sealed-at-utc")
    return parser.parse_args()


def load_request(args: argparse.Namespace) -> ProspectiveRequest:
    payload = json.loads(Path(args.config).read_text(encoding="utf-8"))
    payload.update(
        {
            "output_dir": args.output,
            "run_id": args.run_id,
            "git_commit": args.git_commit,
            "code_sha256": args.code_sha256,
            "config_sha256": args.config_sha256,
            "p4_artifact_sha256": args.p4_artifact_sha256,
            "p4_selected_oof_candidate_id": args.p4_selected_candidate,
            "p4_promotion_status": "NOT_PROMOTED",
        }
    )
    return ProspectiveRequest.model_validate(payload)


def load_context(args: argparse.Namespace) -> P4LineageContext:
    return P4LineageContext(
        p4_status="PASS",
        p4_promotion_status="NOT_PROMOTED",
        p4_selected_oof_candidate_id=args.p4_selected_candidate,
        p4_response_file_sha256=args.p4_response_sha256,
        p4_sha256sums_sha256=args.p4_sha256sums_sha256,
        p4_candidate_aggregates_file_sha256=args.p4_aggregates_sha256,
    )


def main() -> int:
    args = parse_args()
    response = persist_prospective_lock(
        load_request(args),
        load_context(args),
        sealed_at_utc=args.sealed_at_utc,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
