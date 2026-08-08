from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from loto.sktime_campaign.approval_authorization import (
    ApprovalAuthorizationRequest,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256sums(directory: Path) -> None:
    path = directory / "SHA256SUMS"
    if not path.is_file():
        raise RuntimeError(f"missing SHA256SUMS: {directory}")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        if name in seen:
            raise RuntimeError(f"duplicate SHA256SUMS path: {name}")
        seen.add(name)
        artifact = directory / name
        if not artifact.is_file() or _sha256(artifact) != expected:
            raise RuntimeError(f"SHA-256 mismatch: {artifact}")
    expected_files = {
        item.name for item in directory.iterdir() if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise RuntimeError("P6 SHA256SUMS coverage mismatch")


def _p6_evidence(directory: Path) -> dict[str, Any]:
    _verify_sha256sums(directory)
    decision_path = directory / "PROMOTION_DECISION.json"
    response_path = directory / "response.json"
    decision = _load_json(decision_path)
    response = _load_json(response_path)
    if decision.get("decision") != "ELIGIBLE_FOR_HUMAN_APPROVAL":
        raise RuntimeError("P6 decision is not eligible for human approval")
    if decision.get("eligible_for_human_approval") is not True:
        raise RuntimeError("P6 eligibility flag is not true")
    if decision.get("human_approval_required") is not True:
        raise RuntimeError("P6 did not require human approval")
    if decision.get("human_approval_granted") is not False:
        raise RuntimeError("P6 incorrectly claims human approval")
    if decision.get("registry_write_allowed") is not False:
        raise RuntimeError("P6 incorrectly enabled registry write")
    if decision.get("promotion_status") != "NOT_PROMOTED":
        raise RuntimeError("P6 incorrectly claims promotion")
    if response.get("status") != "PASS":
        raise RuntimeError("P6 response status is not PASS")
    if response.get("decision") != decision.get("decision"):
        raise RuntimeError("P6 response and decision disagree")
    return {
        "p6_bundle_sha256": _sha256(directory / "SHA256SUMS"),
        "p6_decision_sha256": _sha256(decision_path),
        "p6_run_id": str(response["run_id"]),
        "shadow_candidate_id": str(decision["shadow_candidate_id"]),
        "decision": "ELIGIBLE_FOR_HUMAN_APPROVAL",
        "eligible_for_human_approval": True,
        "human_approval_required": True,
        "human_approval_granted": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p6-dir", type=Path, required=True)
    parser.add_argument("--policy-config", type=Path, required=True)
    parser.add_argument("--subject-config", type=Path, required=True)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--approval", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--requested-at-utc", required=True)
    parser.add_argument("--expires-at-utc", required=True)
    parser.add_argument("--authorization-nonce", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    p6 = _p6_evidence(args.p6_dir.resolve())
    subject = _load_json(args.subject_config)
    if subject.get("shadow_candidate_id") != p6["shadow_candidate_id"]:
        raise RuntimeError("registry subject differs from P6 shadow candidate")
    approvals = [_load_json(path) for path in args.approval]
    payload = {
        "schema_version": "1.0",
        "operation": "issue_registry_authorization",
        "output_dir": args.evidence_output_dir,
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "allowed_signers_sha256": _sha256(args.allowed_signers),
        "approval_requested_at_utc": args.requested_at_utc,
        "authorization_expires_at_utc": args.expires_at_utc,
        "authorization_nonce": args.authorization_nonce,
        "p6": p6,
        "subject": subject,
        "policy": _load_json(args.policy_config),
        "approvals": approvals,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
    }
    request = ApprovalAuthorizationRequest.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"SKTIME_P7_REQUEST={args.output}")
    print(f"SKTIME_P7_P6_RUN_ID={request.p6.p6_run_id}")
    print(f"SKTIME_P7_SHADOW_CANDIDATE={request.p6.shadow_candidate_id}")


if __name__ == "__main__":
    main()
