from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any, Mapping

EXPECTED_SELECTED_CANDIDATE = "catboost_seed_mean"
EXPECTED_BEST_TRIAL = 14
EXPECTED_BEST_OBJECTIVE = 2.659176845649281
EXPECTED_TRIAL_COUNT = 20
EXPECTED_TARGET_TRANSFORMS_IDX = 2
EXPECTED_MLFORECAST_VERSION = "1.1.0"
EXPECTED_RUNNER_SHA256 = "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
EXPECTED_EXPERIMENT_GIT_COMMIT = "179bcbc9a51a60f0badfe7faa25f3818ab686229"
EXPECTED_LEGACY_FROZEN_SHA256 = "f406422fee3bc426c406443fa74f41a77361eed8987b00ce8143cd87b5d34abf"

DIFFERENCES_CLASS = "mlforecast.target_transforms.Differences"
SCALER_CLASS = "mlforecast.target_transforms.LocalStandardScaler"
LEGACY_OBJECT_STATES: Mapping[str, Mapping[str, Any]] = {
    DIFFERENCES_CLASS: {"differences": [1]},
}


class CanonicalBridgeError(RuntimeError):
    """Raised when Phase 7 canonical bridge evidence does not fail-closed verify."""


def _load_semantic_config(repo: Path) -> Any:
    path = repo / "src" / "loto" / "evaluation" / "semantic_config.py"
    if not path.is_file():
        raise CanonicalBridgeError(f"semantic serializer missing: {path}")
    spec = importlib.util.spec_from_file_location("phase7_semantic_config_v1", path)
    if spec is None or spec.loader is None:
        raise CanonicalBridgeError(f"cannot load semantic serializer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_class(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("<") or " object at 0x" not in value:
        raise CanonicalBridgeError("frozen target transform is not a legacy object repr")
    return value[1:].split(" object at 0x", 1)[0]


def _require_trial_contract(trial_comparison: Mapping[str, Any]) -> None:
    if int(trial_comparison.get("trial_count_expected", -1)) != EXPECTED_TRIAL_COUNT:
        raise CanonicalBridgeError("frozen trial count mismatch")
    if int(trial_comparison.get("trial_count_replay", -1)) != EXPECTED_TRIAL_COUNT:
        raise CanonicalBridgeError("replay trial count mismatch")
    for key in ("numbers_same", "states_same", "objectives_same", "params_same"):
        if trial_comparison.get(key) is not True:
            raise CanonicalBridgeError(f"trial comparison failed: {key}")
    if int(trial_comparison.get("param_diff_rows", -1)) != 0:
        raise CanonicalBridgeError("trial parameter diff rows are non-zero")


def _require_frozen_transform_contract(frozen_config: Mapping[str, Any]) -> None:
    try:
        transforms = frozen_config["mlf_init_params"]["target_transforms"]
    except (KeyError, TypeError) as exc:
        raise CanonicalBridgeError("frozen target transform contract missing") from exc
    if not isinstance(transforms, list) or len(transforms) != 2:
        raise CanonicalBridgeError("frozen target transform count mismatch")
    if _legacy_class(transforms[0]) != DIFFERENCES_CLASS:
        raise CanonicalBridgeError("frozen Differences class mismatch")
    if _legacy_class(transforms[1]) != SCALER_CLASS:
        raise CanonicalBridgeError("frozen LocalStandardScaler class mismatch")


def verify_phase7_canonical_bridge(
    *,
    repo: Path,
    frozen_config: Mapping[str, Any],
    replay_config: Mapping[str, Any],
    legacy_frozen_sha256: str,
    legacy_replay_sha256: str,
    selected_candidate: str,
    frozen_best_trial: int,
    replay_best_trial: int,
    frozen_best_objective: float,
    replay_best_objective: float,
    trial_comparison: Mapping[str, Any],
    replay_best_params: Mapping[str, Any],
    mlforecast_version: str | None,
    runner_sha256: str,
    experiment_git_commit: str,
) -> dict[str, Any]:
    """Verify the frozen/replay config bridge without weakening legacy evidence.

    The frozen `Differences` constructor state was lost by the historical
    `default=str` serialization.  This function therefore bridges it only after
    independent Phase 7 contract checks succeed, and uses the explicitly pinned
    verified state `differences=[1]` rather than inferring state from replay.
    """

    if selected_candidate != EXPECTED_SELECTED_CANDIDATE:
        raise CanonicalBridgeError("selected candidate mismatch")
    if legacy_frozen_sha256 != EXPECTED_LEGACY_FROZEN_SHA256:
        raise CanonicalBridgeError("legacy frozen semantic SHA mismatch")
    if runner_sha256 != EXPECTED_RUNNER_SHA256:
        raise CanonicalBridgeError("runner SHA mismatch")
    if experiment_git_commit != EXPECTED_EXPERIMENT_GIT_COMMIT:
        raise CanonicalBridgeError("experiment commit mismatch")
    if mlforecast_version != EXPECTED_MLFORECAST_VERSION:
        raise CanonicalBridgeError("MLForecast version mismatch")
    if int(frozen_best_trial) != EXPECTED_BEST_TRIAL:
        raise CanonicalBridgeError("frozen best trial mismatch")
    if int(replay_best_trial) != EXPECTED_BEST_TRIAL:
        raise CanonicalBridgeError("replay best trial mismatch")
    if not math.isclose(
        float(frozen_best_objective),
        EXPECTED_BEST_OBJECTIVE,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise CanonicalBridgeError("frozen best objective mismatch")
    if not math.isclose(
        float(replay_best_objective),
        EXPECTED_BEST_OBJECTIVE,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise CanonicalBridgeError("replay best objective mismatch")

    _require_trial_contract(trial_comparison)
    if int(replay_best_params.get("target_transforms_idx", -1)) != EXPECTED_TARGET_TRANSFORMS_IDX:
        raise CanonicalBridgeError("best trial target_transforms_idx mismatch")
    _require_frozen_transform_contract(frozen_config)

    semantic = _load_semantic_config(repo)
    frozen_document = semantic.canonical_semantic_document_v1(
        frozen_config,
        legacy_object_states=LEGACY_OBJECT_STATES,
    )
    replay_document = semantic.canonical_semantic_document_v1(replay_config)
    frozen_sha = semantic.canonical_semantic_sha256_v1(
        frozen_config,
        legacy_object_states=LEGACY_OBJECT_STATES,
    )
    replay_sha = semantic.canonical_semantic_sha256_v1(replay_config)
    if frozen_sha != replay_sha:
        raise CanonicalBridgeError("canonical semantic SHA mismatch")

    return {
        "legacy_semantic_sha256_frozen": legacy_frozen_sha256,
        "legacy_semantic_sha256_replay": legacy_replay_sha256,
        "canonical_semantic_schema": semantic.SEMANTIC_CONFIG_SCHEMA_V1,
        "canonical_semantic_sha256_frozen": frozen_sha,
        "canonical_semantic_sha256_replay": replay_sha,
        "canonical_semantic_match": True,
        "legacy_hash_match": legacy_frozen_sha256 == legacy_replay_sha256,
        "frozen_canonical_document": frozen_document,
        "replay_canonical_document": replay_document,
        "bridge_state_source": "explicit_verified_phase7_contract",
        "differences_state": [1],
        "safe_to_continue_holdout": False,
    }
