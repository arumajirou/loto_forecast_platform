from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from loto.autogluon_campaign.holdout_prospective import (
    HoldoutProspectiveError,
    _empty,
    _tree_hash,
    _verify_hashes,
    _write,
    _write_evidence,
)
from loto.autogluon_campaign.promotion_eligibility_contract import (
    PROMOTION_SCHEMA,
    PromotionEligibilityError,
    PromotionPolicy,
    validate_window_evidence,
)
from loto.autogluon_campaign.promotion_eligibility_io import (
    load_json,
    read_scoring_window,
)
from loto.autogluon_campaign.promotion_eligibility_rules import (
    evaluate_promotion_rules,
)


@dataclass(frozen=True)
class PromotionEligibilityResult:
    output_dir: str
    decision_path: str
    status: str
    decision: str
    reason_code: str
    selected_candidate_id: str


def create_promotion_eligibility(
    *,
    holdout_score_dir: Path,
    prospective_score_dirs: Sequence[Path],
    output_dir: Path,
    policy: PromotionPolicy = PromotionPolicy(),
    run_id: str,
    now: datetime | None = None,
) -> PromotionEligibilityResult:
    if not run_id.strip():
        raise PromotionEligibilityError("RUN_ID_REQUIRED", run_id)

    holdout = read_scoring_window(holdout_score_dir)
    if holdout["stage"] != "holdout":
        raise PromotionEligibilityError("HOLDOUT_STAGE_REQUIRED", str(holdout["stage"]))

    prospective_pairs = [
        (path.resolve(), read_scoring_window(path)) for path in prospective_score_dirs
    ]
    prospective_pairs.sort(key=lambda pair: min(pair[1]["draw_ids"]))
    prospective = [item for _, item in prospective_pairs]
    window_evidence = {"holdout": holdout, "prospective": prospective}
    validate_window_evidence(window_evidence)

    aggregate, rules, decision = evaluate_promotion_rules(
        window_evidence=window_evidence,
        policy=policy,
    )
    candidate_id = holdout["selected_candidate_id"]
    root = _empty(output_dir)
    created_at = now or datetime.now(timezone.utc)
    payloads = {
        "REQUEST_METADATA.json": {
            "schema_version": PROMOTION_SCHEMA,
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
            "policy": policy.model_dump(mode="json"),
        },
        "UPSTREAM_LINEAGE.json": {
            "holdout": {
                "source_run_id": holdout["source_run_id"],
                "source_tree_sha256": holdout["source_tree_sha256"],
                "source_report_sha256": holdout["source_report_sha256"],
            },
            "prospective": [
                {
                    "source_run_id": item["source_run_id"],
                    "source_tree_sha256": item["source_tree_sha256"],
                    "source_report_sha256": item["source_report_sha256"],
                }
                for item in prospective
            ],
        },
        "WINDOW_EVIDENCE.json": window_evidence,
        "AGGREGATED_METRICS.json": aggregate,
        "RULE_EVALUATION.json": {"rules": rules},
        "PROMOTION_DECISION.json": decision,
        "response.json": {
            "status": decision["status"],
            "decision": decision["decision"],
            "reason_code": decision["reason_code"],
            "selected_candidate_id": candidate_id,
            "registry_write_allowed": False,
        },
    }
    for name, payload in payloads.items():
        _write(root / name, payload)
    _write_evidence(root, list(payloads))

    source_hashes_after = {
        holdout["source_run_id"]: _tree_hash(holdout_score_dir.resolve()),
        **{item["source_run_id"]: _tree_hash(path) for path, item in prospective_pairs},
    }
    expected_hashes = {
        holdout["source_run_id"]: holdout["source_tree_sha256"],
        **{item["source_run_id"]: item["source_tree_sha256"] for item in prospective},
    }
    if source_hashes_after != expected_hashes:
        raise PromotionEligibilityError("UPSTREAM_SOURCE_MUTATED", str(source_hashes_after))

    verify_promotion_eligibility(root)
    return PromotionEligibilityResult(
        output_dir=str(root),
        decision_path=str(root / "PROMOTION_DECISION.json"),
        status=str(decision["status"]),
        decision=str(decision["decision"]),
        reason_code=str(decision["reason_code"]),
        selected_candidate_id=candidate_id,
    )


def verify_promotion_eligibility(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = {
        "REQUEST_METADATA.json",
        "UPSTREAM_LINEAGE.json",
        "WINDOW_EVIDENCE.json",
        "AGGREGATED_METRICS.json",
        "RULE_EVALUATION.json",
        "PROMOTION_DECISION.json",
        "response.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }
    try:
        observed = _verify_hashes(root, "PROMOTION")
    except HoldoutProspectiveError as exc:
        raise PromotionEligibilityError(exc.code, str(exc)) from exc
    if observed != required:
        raise PromotionEligibilityError("PROMOTION_FILE_SET_MISMATCH", str(observed))

    request = load_json(root / "REQUEST_METADATA.json")
    policy = PromotionPolicy.model_validate(request["policy"])
    window_evidence = load_json(root / "WINDOW_EVIDENCE.json")
    aggregate, rules, decision = evaluate_promotion_rules(
        window_evidence=window_evidence,
        policy=policy,
    )
    if load_json(root / "AGGREGATED_METRICS.json") != aggregate:
        raise PromotionEligibilityError("AGGREGATED_METRICS_MISMATCH", str(root))
    if load_json(root / "RULE_EVALUATION.json") != {"rules": rules}:
        raise PromotionEligibilityError("RULE_EVALUATION_MISMATCH", str(root))
    if load_json(root / "PROMOTION_DECISION.json") != decision:
        raise PromotionEligibilityError("PROMOTION_DECISION_MISMATCH", str(root))

    response = load_json(root / "response.json")
    expected_response = {
        "status": decision["status"],
        "decision": decision["decision"],
        "reason_code": decision["reason_code"],
        "selected_candidate_id": decision["selected_candidate_id"],
        "registry_write_allowed": False,
    }
    if response != expected_response:
        raise PromotionEligibilityError("PROMOTION_RESPONSE_MISMATCH", str(root))
    return {
        "status": decision["status"],
        "decision": decision["decision"],
        "reason_code": decision["reason_code"],
        "decision_sha256": decision["decision_sha256"],
        "tree_sha256": _tree_hash(root),
    }


__all__ = [
    "PromotionEligibilityError",
    "PromotionEligibilityResult",
    "PromotionPolicy",
    "create_promotion_eligibility",
    "verify_promotion_eligibility",
]
