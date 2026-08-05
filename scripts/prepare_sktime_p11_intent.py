from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from loto.sktime_campaign.deployment_canary import DeploymentState
from loto.sktime_campaign.primary_promotion_authorization import (
    DeploymentPrecondition,
    P10ReviewEvidence,
    PromotionPolicy,
    canonical_sha256,
    primary_promotion_intent,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256sums(directory: Path) -> None:
    path = directory / "SHA256SUMS"
    if not path.is_file():
        raise ValueError(f"missing SHA256SUMS: {directory}")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        target = directory / name
        if name in seen or not target.is_file() or sha256(target) != expected:
            raise ValueError(f"P10 SHA mismatch: {name}")
        seen.add(name)
    expected_names = {
        item.name
        for item in directory.iterdir()
        if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_names:
        raise ValueError("P10 SHA256SUMS coverage mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p10-dir", required=True, type=Path)
    parser.add_argument("--deployment-state", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--allowed-signers-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--requested-at-utc", required=True)
    parser.add_argument("--expires-at-utc", required=True)
    parser.add_argument("--authorization-nonce", required=True)
    args = parser.parse_args()

    verify_sha256sums(args.p10_dir)
    response = json.loads((args.p10_dir / "response.json").read_text())
    decision = json.loads(
        (args.p10_dir / "PRIMARY_PROMOTION_REVIEW_DECISION.json").read_text()
    )
    aggregate = json.loads(
        (args.p10_dir / "AGGREGATED_METRICS.json").read_text()
    )
    p9 = json.loads((args.p10_dir / "P9_LINEAGE.json").read_text())
    if response.get("decision") != "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW":
        raise ValueError("P10 is not eligible for primary-promotion review")
    if response.get("primary_promotion_eligible") is not True:
        raise ValueError("P10 response does not mark promotion eligibility")
    if decision.get("primary_promotion_eligible") is not True:
        raise ValueError("P10 formal decision is not eligible")
    if response.get("primary_promotion_executed") is not False:
        raise ValueError("P10 already claims primary promotion")
    if response.get("primary_binding_changed") is not False:
        raise ValueError("P10 already claims primary binding change")

    subject = p9["subject"]
    candidate = aggregate["candidate_metrics"][subject["shadow_candidate_id"]]
    mean = candidate["mean"]
    worst = candidate["worst"]
    p10_payload = {
        "schema_version": "1.0",
        "p10_bundle_sha256": sha256(args.p10_dir / "SHA256SUMS"),
        "p10_decision_sha256": sha256(
            args.p10_dir / "PRIMARY_PROMOTION_REVIEW_DECISION.json"
        ),
        "p10_aggregated_metrics_sha256": sha256(
            args.p10_dir / "AGGREGATED_METRICS.json"
        ),
        "p10_baseline_comparison_sha256": sha256(
            args.p10_dir / "BASELINE_COMPARISON.json"
        ),
        "p10_window_evidence_sha256": sha256(
            args.p10_dir / "WINDOW_EVIDENCE.json"
        ),
        "p9_activation_id": p9["activation_id"],
        "decision": response["decision"],
        "eligible_for_primary_promotion_review": True,
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "prediction_publication_allowed": False,
        "weighted_hit_at_1": mean["hit_at_1"],
        "worst_window_hit_at_1": worst["hit_at_1"],
        "weighted_all_position_hit_at_1": mean["all_position_hit_at_1"],
        "weighted_mae": mean["mae"],
        "weighted_mse": mean["mse"],
        "weighted_rmse": mean["rmse"],
        "window_count": response["window_count"],
        "draw_count": response["total_draws"],
        "subject": subject,
    }
    p10_evidence = P10ReviewEvidence.model_validate(p10_payload)

    deployment_state = DeploymentState.model_validate_json(
        args.deployment_state.read_text(encoding="utf-8")
    )
    if deployment_state.canary_binding is None:
        raise ValueError("deployment state has no active canary")
    deployment_payload = {
        "schema_version": "1.0",
        "deployment_target": deployment_state.deployment_target,
        "deployment_state_sha256": deployment_state.state_sha256,
        "deployment_generation": deployment_state.generation,
        "primary_binding": (
            deployment_state.primary_binding.model_dump(mode="json")
            if deployment_state.primary_binding
            else None
        ),
        "canary_binding": deployment_state.canary_binding.model_dump(mode="json"),
    }
    precondition = DeploymentPrecondition.model_validate(
        {
            **deployment_payload,
            "state_snapshot_sha256": canonical_sha256(deployment_payload),
        }
    )
    policy = PromotionPolicy.model_validate_json(
        args.policy.read_text(encoding="utf-8")
    )
    allowed_signers_sha = sha256(args.allowed_signers_file)
    common = {
        "schema_version": "1.0",
        "operation": "authorize_primary_promotion",
        "output_dir": args.evidence_output_dir,
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "allowed_signers_file": str(args.allowed_signers_file),
        "allowed_signers_sha256": allowed_signers_sha,
        "requested_at_utc": args.requested_at_utc,
        "expires_at_utc": args.expires_at_utc,
        "authorization_nonce": args.authorization_nonce,
        "p10": p10_evidence.model_dump(mode="json"),
        "deployment": precondition.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
    }
    request_like = SimpleNamespace(
        **{
            **common,
            "p10": p10_evidence,
            "deployment": precondition,
            "policy": policy,
        }
    )
    intent = primary_promotion_intent(request_like)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "request-base.json").write_text(
        json.dumps(common, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "PRIMARY_PROMOTION_INTENT.json").write_text(
        json.dumps(intent, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "PRIMARY_PROMOTION_INTENT_SHA256").write_text(
        canonical_sha256(intent) + "\n",
        encoding="utf-8",
    )
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
