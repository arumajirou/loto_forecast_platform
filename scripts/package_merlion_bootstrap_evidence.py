from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.bootstrap_evidence import package_bootstrap_evidence
from loto.merlion_campaign.bootstrap_evidence_verify import verify_bootstrap_evidence_zip
from loto.merlion_campaign.bootstrap_resume import write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--environment-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    args = parser.parse_args()
    result = package_bootstrap_evidence(
        args.run_dir,
        args.environment_dir,
        args.output,
        run_id=args.run_id,
    )
    verification = verify_bootstrap_evidence_zip(args.output)
    write_json(args.verification, verification)
    print(f"BOOTSTRAP_EVIDENCE_STATUS={result['status']}")
    print(f"BOOTSTRAP_EVIDENCE_ZIP={args.output.resolve()}")
    print(f"BOOTSTRAP_EVIDENCE_SHA256={result['zip_sha256']}")
    print(f"BOOTSTRAP_EVIDENCE_VERIFICATION={args.verification.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
