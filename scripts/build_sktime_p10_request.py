from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from loto.sktime_campaign.canary_evaluation import CanaryEvaluationRequest


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256sums(directory: Path) -> None:
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise ValueError(f"missing SHA256SUMS: {directory}")
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        path = directory / name
        if name in seen or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"P9 SHA mismatch: {name}")
        seen.add(name)
    expected_names = {
        item.name for item in directory.iterdir() if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_names:
        raise ValueError("P9 SHA256SUMS coverage mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p9-dir", required=True, type=Path)
    parser.add_argument("--window", action="append", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--evaluated-at-utc", required=True)
    args = parser.parse_args()

    verify_sha256sums(args.p9_dir)
    response = json.loads((args.p9_dir / "response.json").read_text())
    receipt = json.loads((args.p9_dir / "ACTIVATION_RECEIPT.json").read_text())
    post_state = json.loads((args.p9_dir / "POST_DEPLOYMENT_STATE.json").read_text())
    if response.get("status") != "PASS":
        raise ValueError("P9 status is not PASS")
    if response.get("decision") != "SHADOW_CANARY_ACTIVATED":
        raise ValueError("P9 did not activate a new shadow canary")
    if response.get("promotion_status") != "CANARY_ACTIVE_NOT_PRIMARY":
        raise ValueError("P9 promotion status mismatch")
    if response.get("primary_binding_unchanged") is not True:
        raise ValueError("P9 changed the primary binding")
    if response.get("prediction_publication_allowed") is not False:
        raise ValueError("P9 enabled prediction publication")
    canary = post_state.get("canary_binding")
    if not canary or not canary.get("subject"):
        raise ValueError("P9 post-state lacks a canary subject")
    if receipt.get("activation_id") != response.get("activation_id"):
        raise ValueError("P9 activation ID mismatch")

    p9 = {
        "schema_version": "1.0",
        "p9_bundle_sha256": sha256(args.p9_dir / "SHA256SUMS"),
        "p9_receipt_sha256": sha256(args.p9_dir / "ACTIVATION_RECEIPT.json"),
        "p9_post_state_sha256": sha256(args.p9_dir / "POST_DEPLOYMENT_STATE.json"),
        "activation_id": receipt["activation_id"],
        "decision": response["decision"],
        "promotion_status": response["promotion_status"],
        "primary_binding_unchanged": True,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "subject": canary["subject"],
    }
    payload = {
        "schema_version": "1.0",
        "operation": "evaluate_shadow_canary",
        "output_dir": args.evidence_output_dir,
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "evaluated_at_utc": args.evaluated_at_utc,
        "p9": p9,
        "policy": json.loads(args.policy.read_text(encoding="utf-8")),
        "windows": [json.loads(path.read_text(encoding="utf-8")) for path in args.window],
    }
    request = CanaryEvaluationRequest.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        request.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
