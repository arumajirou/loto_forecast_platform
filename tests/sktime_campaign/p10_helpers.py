from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from loto.sktime_campaign.canary_evaluation import (
    CanaryEvaluationRequest,
    LockedCandidatePrediction,
    PositionRange,
    ShadowEvaluationWindow,
    canonical_sha256,
    prediction_lock_payload,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64
ACTIVATION_ID = "1" * 64
SHADOW_ID = "shadow-model"


def _candidate(
    candidate_id: str,
    values: list[list[int]],
    seed: int | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "role": "shadow" if candidate_id == SHADOW_ID else "baseline",
        "seed": seed,
        "actuals_known_at_prediction": False,
        "prediction_scope": "SHADOW_ONLY",
        "values": values,
    }


def make_window_payload(
    index: int,
    *,
    shadow_values: list[list[int]] | None = None,
    baseline_values: list[list[int]] | None = None,
) -> dict[str, Any]:
    actuals = [[2 + index, 5 + index]]
    shadow_values = shadow_values or copy.deepcopy(actuals)
    baseline_values = baseline_values or [[0, 0]]
    predictions = [
        _candidate(SHADOW_ID, shadow_values),
        _candidate("random", baseline_values, 1),
        _candidate("random", baseline_values, 2),
        _candidate("random", baseline_values, 3),
        _candidate("fixed", baseline_values),
        _candidate("mean", baseline_values),
        _candidate("median", baseline_values),
        _candidate("last", baseline_values),
        _candidate("frequency", baseline_values),
        _candidate("seasonal_naive", baseline_values),
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "window_id": f"window-{index}",
        "activation_id": ACTIVATION_ID,
        "shadow_candidate_id": SHADOW_ID,
        "prediction_locked_at_utc": f"2026-08-0{index}T00:00:00Z",
        "actuals_revealed_at_utc": f"2026-08-0{index}T01:00:00Z",
        "prediction_lock_sha256": "0" * 64,
        "actual_source_sha256": HEX_A,
        "history_snapshot_sha256": HEX_B,
        "prediction_code_sha256": HEX_C,
        "draw_ids": [f"draw-{index}"],
        "position_ranges": [
            {"minimum": 0, "maximum": 9},
            {"minimum": 0, "maximum": 9},
        ],
        "actuals": actuals,
        "predictions": predictions,
    }
    temporary = ShadowEvaluationWindow.model_construct(
        **{
            **payload,
            "position_ranges": [
                PositionRange.model_validate(item)
                for item in payload["position_ranges"]
            ],
            "predictions": [LockedCandidatePrediction.model_validate(item) for item in predictions],
        }
    )
    payload["prediction_lock_sha256"] = canonical_sha256(prediction_lock_payload(temporary))
    return payload


def reseal_window_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(payload)
    temporary = ShadowEvaluationWindow.model_construct(
        **{
            **payload,
            "position_ranges": [
                PositionRange.model_validate(item)
                for item in payload["position_ranges"]
            ],
            "predictions": [
                LockedCandidatePrediction.model_validate(item)
                for item in payload["predictions"]
            ],
        }
    )
    payload["prediction_lock_sha256"] = canonical_sha256(
        prediction_lock_payload(temporary)
    )
    return payload


def make_request(output_dir: Path, *, windows: int = 3) -> CanaryEvaluationRequest:
    payload = {
        "schema_version": "1.0",
        "operation": "evaluate_shadow_canary",
        "output_dir": str(output_dir),
        "run_id": "p10-test-run",
        "git_commit": "1" * 40,
        "code_sha256": HEX_D,
        "config_sha256": HEX_E,
        "evaluated_at_utc": "2026-08-10T00:00:00Z",
        "p9": {
            "schema_version": "1.0",
            "p9_bundle_sha256": HEX_A,
            "p9_receipt_sha256": HEX_B,
            "p9_post_state_sha256": HEX_C,
            "activation_id": ACTIVATION_ID,
            "decision": "SHADOW_CANARY_ACTIVATED",
            "promotion_status": "CANARY_ACTIVE_NOT_PRIMARY",
            "primary_binding_unchanged": True,
            "prediction_publication_allowed": False,
            "automatic_primary_promotion": False,
            "subject": {
                "registry_target": "file+json:///registry.json",
                "model_id": "model-a",
                "model_revision": "1234567",
                "shadow_candidate_id": SHADOW_ID,
                "model_artifact_sha256": HEX_D,
                "data_snapshot_sha256": HEX_E,
                "runtime_environment_sha256": HEX_F,
                "code_sha256": HEX_C,
            },
        },
        "policy": {
            "minimum_windows": 3,
            "minimum_total_draws": 3,
            "minimum_weighted_hit_at_1": 0.9,
            "minimum_worst_window_hit_at_1": 0.9,
            "maximum_weighted_mae": 1.0,
            "require_all_baseline_superiority": True,
            "strict_improvement_over_at_least_one_baseline": True,
            "primary_promotion_executed": False,
            "primary_binding_changed": False,
            "prediction_publication_allowed": False,
            "automatic_primary_promotion": False,
            "automatic_retraining": False,
            "automatic_rollback": False,
        },
        "windows": [make_window_payload(index) for index in range(1, windows + 1)],
    }
    return CanaryEvaluationRequest.model_validate(payload)
