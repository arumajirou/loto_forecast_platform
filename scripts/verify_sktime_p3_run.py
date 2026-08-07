from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.rolling_artifacts import P3VerificationError, verify_p3
from loto.sktime_campaign.rolling_origin import RollingOriginRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a sktime P3 evidence bundle.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--validation-artifact-sha256", required=True)
    parser.add_argument(
        "--allow-nonpass",
        action="store_true",
        help="Verify PARTIAL/FAILED evidence without granting formal certification.",
    )
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
    try:
        report = verify_p3(
            Path(args.output),
            request,
            formal=not args.allow_nonpass,
        )
    except (OSError, ValueError, P3VerificationError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
