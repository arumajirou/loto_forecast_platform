from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.rolling_artifacts import persist_p3
from loto.sktime_campaign.rolling_origin import RollingOriginRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run sktime P3 Train-only OOF and Holdout prediction locking."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--validation-artifact-sha256", required=True)
    return parser.parse_args()


def load_request(args: argparse.Namespace) -> RollingOriginRequest:
    payload = json.loads(Path(args.config).read_text(encoding="utf-8"))
    payload.update(
        {
            "output_dir": args.output,
            "run_id": args.run_id,
            "git_commit": args.git_commit,
            "code_sha256": args.code_sha256,
            "config_sha256": args.config_sha256,
            "validation_artifact_sha256": args.validation_artifact_sha256,
        }
    )
    return RollingOriginRequest.model_validate(payload)


def main() -> int:
    args = parse_args()
    request = load_request(args)
    response = persist_p3(request)
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
