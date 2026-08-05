from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.holdout_artifacts import file_sha256, persist_p4
from loto.sktime_campaign.holdout_scoring import (
    HoldoutActuals,
    HoldoutScoringRequest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a sealed sktime P3 Holdout prediction lock."
    )
    parser.add_argument("--actuals-config", required=True)
    parser.add_argument("--prediction-lock", required=True)
    parser.add_argument("--p3-sha256sums", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--revealed-at-utc", required=True)
    parser.add_argument("--scored-at-utc", required=True)
    return parser.parse_args()


def load_inputs(
    args: argparse.Namespace,
) -> tuple[HoldoutScoringRequest, dict]:
    actuals_path = Path(args.actuals_config).resolve()
    lock_path = Path(args.prediction_lock).resolve()
    p3_sums_path = Path(args.p3_sha256sums).resolve()
    actuals_payload = json.loads(actuals_path.read_text(encoding="utf-8"))
    actuals_payload.update(
        {
            "revealed_at_utc": args.revealed_at_utc,
            "source_sha256": file_sha256(actuals_path),
        }
    )
    actuals = HoldoutActuals.model_validate(actuals_payload)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    request = HoldoutScoringRequest(
        output_dir=args.output,
        run_id=args.run_id,
        git_commit=args.git_commit,
        code_sha256=args.code_sha256,
        config_sha256=args.config_sha256,
        prediction_lock_file_sha256=file_sha256(lock_path),
        expected_lock_seal_sha256=lock["seal_sha256"],
        p3_sha256sums_sha256=file_sha256(p3_sums_path),
        scored_at_utc=args.scored_at_utc,
        actuals=actuals,
    )
    return request, lock


def main() -> int:
    args = parse_args()
    request, lock = load_inputs(args)
    response = persist_p4(request, lock, formal=True)
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
