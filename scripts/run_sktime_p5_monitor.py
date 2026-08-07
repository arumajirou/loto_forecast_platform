from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.prospective import (
    DriftPolicy,
    ProspectiveActuals,
    ProspectiveMonitoringRequest,
)
from loto.sktime_campaign.prospective_artifacts import (
    persist_prospective_monitor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a sealed P5 lock and produce a drift report."
    )
    parser.add_argument("--actuals-config", required=True)
    parser.add_argument("--prediction-lock", required=True)
    parser.add_argument("--holdout-reference-metrics", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revealed-at-utc")
    return parser.parse_args()


def load_request(args: argparse.Namespace) -> ProspectiveMonitoringRequest:
    config = json.loads(Path(args.actuals_config).read_text(encoding="utf-8"))
    actuals_payload = dict(config["actuals"])
    if args.revealed_at_utc:
        actuals_payload["revealed_at_utc"] = args.revealed_at_utc
    lock = json.loads(Path(args.prediction_lock).read_text(encoding="utf-8"))
    reference = json.loads(
        Path(args.holdout_reference_metrics).read_text(encoding="utf-8")
    )
    return ProspectiveMonitoringRequest(
        run_id=args.run_id,
        prediction_lock=lock,
        actuals=ProspectiveActuals.model_validate(actuals_payload),
        holdout_reference_metrics=reference,
        policy=DriftPolicy.model_validate(config.get("policy", {})),
    )


def main() -> int:
    args = parse_args()
    response = persist_prospective_monitor(
        load_request(args),
        Path(args.output),
    )
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
