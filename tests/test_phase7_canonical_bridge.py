from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "phase7_semantic_diagnosis" / "canonical_bridge.py"
SPEC = importlib.util.spec_from_file_location("phase7_canonical_bridge", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

Differences = type("Differences", (), {"__module__": "mlforecast.target_transforms"})
LocalStandardScaler = type(
    "LocalStandardScaler", (), {"__module__": "mlforecast.target_transforms"}
)


def differences(values: list[int]):
    obj = Differences()
    obj.differences = values
    return obj


def scaler():
    return LocalStandardScaler()


def config(target_transforms):
    return {
        "mlf_fit_params": {"static_features": []},
        "mlf_init_params": {
            "date_features": None,
            "lag_transforms": None,
            "lags": [1],
            "num_threads": 1,
            "target_transforms": target_transforms,
        },
        "model_params": {
            "colsample_bylevel": 0.3647267818084223,
            "depth": 3,
            "learning_rate": 0.022109361986862856,
            "min_data_in_leaf": 95.95708821814695,
            "n_estimators": 821,
            "silent": True,
            "subsample": 0.8535280164377872,
        },
    }


def frozen_config():
    return config(
        [
            "<mlforecast.target_transforms.Differences object at 0x000002785DF348A0>",
            "<mlforecast.target_transforms.LocalStandardScaler object at 0x000002785F2B8590>",
        ]
    )


def replay_config(difference: int = 1):
    return config([differences([difference]), scaler()])


def trial_comparison():
    return {
        "trial_count_expected": 20,
        "trial_count_replay": 20,
        "numbers_same": True,
        "states_same": True,
        "objectives_same": True,
        "params_same": True,
        "param_diff_rows": 0,
    }


def verify(**overrides):
    kwargs = {
        "repo": REPO,
        "frozen_config": frozen_config(),
        "replay_config": replay_config(),
        "legacy_frozen_sha256": MOD.EXPECTED_LEGACY_FROZEN_SHA256,
        "legacy_replay_sha256": "7a0add8cad6f943a3202a7182093010df5ea4ecc32680e0f8ef4903e1f457edf",
        "selected_candidate": MOD.EXPECTED_SELECTED_CANDIDATE,
        "frozen_best_trial": 14,
        "replay_best_trial": 14,
        "frozen_best_objective": MOD.EXPECTED_BEST_OBJECTIVE,
        "replay_best_objective": MOD.EXPECTED_BEST_OBJECTIVE,
        "trial_comparison": trial_comparison(),
        "replay_best_params": {"target_transforms_idx": 2},
        "mlforecast_version": "1.1.0",
        "runner_sha256": MOD.EXPECTED_RUNNER_SHA256,
        "experiment_git_commit": MOD.EXPECTED_EXPERIMENT_GIT_COMMIT,
    }
    kwargs.update(overrides)
    return MOD.verify_phase7_canonical_bridge(**kwargs)


def test_verified_phase7_bridge_produces_equal_v1_hashes_and_preserves_legacy_mismatch() -> None:
    result = verify()

    assert result["canonical_semantic_schema"] == "loto.semantic-config/v1"
    assert result["canonical_semantic_match"] is True
    assert result["canonical_semantic_sha256_frozen"] == result["canonical_semantic_sha256_replay"]
    assert result["legacy_hash_match"] is False
    assert result["bridge_state_source"] == "explicit_verified_phase7_contract"
    assert result["differences_state"] == [1]
    assert result["safe_to_continue_holdout"] is False


def test_bridge_rejects_semantic_change_even_when_legacy_shape_looks_compatible() -> None:
    with pytest.raises(MOD.CanonicalBridgeError, match="canonical semantic SHA mismatch"):
        verify(replay_config=replay_config(2))


def test_bridge_rejects_wrong_target_transform_index_before_state_bridge() -> None:
    with pytest.raises(MOD.CanonicalBridgeError, match="target_transforms_idx"):
        verify(replay_best_params={"target_transforms_idx": 3})


def test_bridge_rejects_version_drift() -> None:
    with pytest.raises(MOD.CanonicalBridgeError, match="MLForecast version mismatch"):
        verify(mlforecast_version="1.1.1")


def test_bridge_rejects_trial_sequence_mismatch() -> None:
    bad = trial_comparison()
    bad["params_same"] = False
    bad["param_diff_rows"] = 1
    with pytest.raises(MOD.CanonicalBridgeError, match="params_same"):
        verify(trial_comparison=bad)


def test_bridge_rejects_unexpected_legacy_frozen_sha() -> None:
    with pytest.raises(MOD.CanonicalBridgeError, match="legacy frozen semantic SHA"):
        verify(legacy_frozen_sha256="0" * 64)
