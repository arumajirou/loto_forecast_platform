from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from loto.merlion_campaign.bootstrap_evidence_verify import verify_bootstrap_evidence_zip
from loto.merlion_campaign.license_review import (
    build_license_review_template,
    parse_dependency_inventory,
)
from loto.merlion_campaign.lock_admission import (
    EVIDENCE_INVENTORY_PATH,
    EVIDENCE_LOCK_PATH,
    read_evidence_payloads,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verification = verify_bootstrap_evidence_zip(args.evidence_zip)
    if verification["evidence_status"] != "BOOTSTRAP_PASS":
        raise SystemExit("BLOCKED: evidence status is not BOOTSTRAP_PASS")
    payloads = read_evidence_payloads(args.evidence_zip)
    rows = parse_dependency_inventory(payloads[EVIDENCE_INVENTORY_PATH])
    template = build_license_review_template(
        rows,
        evidence_zip_sha256=hashlib.sha256(args.evidence_zip.read_bytes()).hexdigest(),
        lock_sha256=hashlib.sha256(payloads[EVIDENCE_LOCK_PATH]).hexdigest(),
    )
    write_json(args.output, template)
    print(f"LICENSE_REVIEW_TEMPLATE={args.output.resolve()}")
    print(f"LICENSE_PACKAGE_COUNT={template['package_count']}")
    print("NEXT_ACTION=complete every package and convert schema to merlion-license-review-v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
