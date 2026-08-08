from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .p7c_analysis import (
    P7CInputError,
    build_remediation_plan,
    write_remediation_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze immutable GluonTS P7B evidence")
    parser.add_argument("--p7b-output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = build_remediation_plan(args.p7b_output)
        identities = write_remediation_outputs(
            args.p7b_output,
            args.output_dir,
            plan,
        )
    except (P7CInputError, ValueError) as exc:
        print(
            f"P7C_INPUT_INVALID={type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "phase": plan.phase,
                "run_id": plan.source.run_id,
                "evidence_state": plan.evidence_state,
                "certification_status": plan.certification_status,
                "verified_model_lifecycles": plan.verified_model_lifecycles,
                "p8_eligible": plan.p8_eligible,
                "output_dir": str(args.output_dir.resolve()),
                "identities": identities,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if plan.p8_eligible:
        return 0
    if plan.evidence_state != "VALID":
        return 20
    return 10


if __name__ == "__main__":
    raise SystemExit(main())
