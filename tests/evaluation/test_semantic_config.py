from __future__ import annotations

import json

import pytest

from loto.evaluation.semantic_config import (
    SEMANTIC_CONFIG_SCHEMA_V1,
    SemanticConfigError,
    canonical_semantic_bytes_v1,
    canonical_semantic_document_v1,
    canonical_semantic_sha256_v1,
)


Differences = type(
    "Differences", (), {"__module__": "mlforecast.target_transforms"}
)
LocalStandardScaler = type(
    "LocalStandardScaler", (), {"__module__": "mlforecast.target_transforms"}
)


def differences(values: list[int]):
    obj = Differences()
    obj.differences = values
    return obj


def scaler():
    return LocalStandardScaler()


def phase7_config(target_transforms):
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


def test_equivalent_live_mlforecast_transforms_have_same_hash() -> None:
    left = phase7_config([differences([1]), scaler()])
    right = phase7_config([differences([1]), scaler()])

    assert canonical_semantic_bytes_v1(left) == canonical_semantic_bytes_v1(right)
    assert canonical_semantic_sha256_v1(left) == canonical_semantic_sha256_v1(right)


def test_differences_constructor_state_changes_hash() -> None:
    one = phase7_config([differences([1]), scaler()])
    two = phase7_config([differences([2]), scaler()])

    assert canonical_semantic_sha256_v1(one) != canonical_semantic_sha256_v1(two)


def test_phase7_legacy_repr_bridge_matches_live_config() -> None:
    frozen = phase7_config(
        [
            "<mlforecast.target_transforms.Differences object at 0x000002785DF348A0>",
            "<mlforecast.target_transforms.LocalStandardScaler object at 0x000002785F2B8590>",
        ]
    )
    replay = phase7_config([differences([1]), scaler()])
    legacy_states = {
        "mlforecast.target_transforms.Differences": {"differences": [1]},
    }

    assert canonical_semantic_sha256_v1(
        frozen, legacy_object_states=legacy_states
    ) == canonical_semantic_sha256_v1(replay)


def test_legacy_parameterized_object_requires_explicit_state() -> None:
    frozen = phase7_config(
        ["<mlforecast.target_transforms.Differences object at 0x1234>", scaler()]
    )

    with pytest.raises(SemanticConfigError, match="explicit state is required"):
        canonical_semantic_sha256_v1(frozen)


def test_unsupported_object_fails_closed_instead_of_stringifying() -> None:
    class Unknown:
        pass

    with pytest.raises(SemanticConfigError, match="explicit adapter"):
        canonical_semantic_sha256_v1({"x": Unknown()})


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(SemanticConfigError, match="NaN or infinity"):
        canonical_semantic_sha256_v1({"x": float("nan")})


def test_document_is_versioned_and_json_is_deterministic() -> None:
    config = {"b": 2, "a": 1}
    document = canonical_semantic_document_v1(config)
    encoded = canonical_semantic_bytes_v1(config)

    assert document["schema"] == SEMANTIC_CONFIG_SCHEMA_V1
    assert json.loads(encoded) == document
    assert encoded == b'{"config":{"a":1,"b":2},"schema":"loto.semantic-config/v1"}'
