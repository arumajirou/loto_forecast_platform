from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from loto.sktime_campaign.deployment_canary import CanaryActivationRequest


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
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        path = directory / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"P8 SHA mismatch: {name}")


def bundle_sha256(directory: Path) -> str:
    return sha256(directory / "SHA256SUMS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p8-dir", required=True, type=Path)
    parser.add_argument("--runtime-probe", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--deployment-state", required=True, type=Path)
    parser.add_argument("--deployment-target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--requested-at-utc", required=True)
    parser.add_argument("--activation-nonce", required=True)
    args = parser.parse_args()

    verify_sha256sums(args.p8_dir)
    response = json.loads((args.p8_dir / "response.json").read_text())
    receipt = json.loads((args.p8_dir / "TRANSACTION_RECEIPT.json").read_text())
    post_state = json.loads((args.p8_dir / "POST_REGISTRY_STATE.json").read_text())
    if response.get("decision") != "REGISTRY_TRANSACTION_COMMITTED":
        raise ValueError("P8 did not commit a new registry transaction")
    if response.get("promotion_status") != "REGISTERED_NOT_DEPLOYED":
        raise ValueError("P8 promotion status mismatch")
    if response.get("deployment_status") != "NOT_DEPLOYED":
        raise ValueError("P8 deployment status mismatch")
    subject = post_state.get("current_binding", {}).get("subject")
    if not subject:
        raise ValueError("P8 post-state lacks current registered subject")
    state_payload = json.loads(args.deployment_state.read_text())
    expected_state_sha = state_payload["state_sha256"]
    p8 = {
        "schema_version": "1.0",
        "p8_bundle_sha256": bundle_sha256(args.p8_dir),
        "p8_receipt_sha256": sha256(args.p8_dir / "TRANSACTION_RECEIPT.json"),
        "p8_post_state_sha256": sha256(args.p8_dir / "POST_REGISTRY_STATE.json"),
        "registry_state_sha256": post_state["state_sha256"],
        "transaction_id": receipt["transaction_id"],
        "decision": response["decision"],
        "promotion_status": response["promotion_status"],
        "deployment_status": response["deployment_status"],
        "subject": subject,
    }
    payload = {
        "schema_version": "1.0",
        "operation": "activate_shadow_canary",
        "output_dir": args.evidence_output_dir,
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "requested_at_utc": args.requested_at_utc,
        "deployment_target": args.deployment_target,
        "expected_deployment_state_sha256": expected_state_sha,
        "activation_nonce": args.activation_nonce,
        "p8": p8,
        "runtime_probe": json.loads(args.runtime_probe.read_text()),
        "policy": json.loads(args.policy.read_text()),
    }
    request = CanaryActivationRequest.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(request.model_dump_json(indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
