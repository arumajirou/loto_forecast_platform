from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from loto.sktime_campaign.approval_artifacts import verify_p7
from loto.sktime_campaign.approval_authorization import (
    ApprovalAuthorizationRequest,
    make_ssh_signature_verifier,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--issued-at-utc", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = ApprovalAuthorizationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    if _sha256(args.allowed_signers) != request.allowed_signers_sha256:
        raise RuntimeError("allowed signers SHA-256 differs from request")
    result = verify_p7(
        args.output,
        request,
        issued_at_utc=args.issued_at_utc,
        signature_verifier=make_ssh_signature_verifier(args.allowed_signers),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
