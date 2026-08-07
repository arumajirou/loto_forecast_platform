from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.merlion_campaign.license_review import finalize_license_review
from loto.merlion_campaign.lock_admission import write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    template = json.loads(args.template.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise SystemExit("BLOCKED: template must be a JSON object")
    review = finalize_license_review(template)
    write_json(args.output, review)
    print(f"LICENSE_REVIEW={args.output.resolve()}")
    print(f"LICENSE_OVERALL_DECISION={review['overall_decision']}")
    return 0 if review["overall_decision"] == "APPROVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
