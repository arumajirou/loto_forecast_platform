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

Differences = type("Differences", (), {"__module__": "mlforecast.target_transforms"})
LocalStandardScaler = type(
    "LocalStandardScaler", (), {"__module__": "mlforecast.target_transforms"}
)
GlobalSklearnTransformer = type(
    "GlobalSklearnTransformer", (), {"__module__": "mlforecast.target_transforms"}
)
FunctionTransformer = type(
    "FunctionTransformer",
    (),
    {"__module__": "sklearn.preprocessing._function_transformer"},
)
ExponentiallyWeightedMean = type(
    "ExponentiallyWeightedMean",
    (),
    {"__module__": "mlforecast.lag_transforms"},
)


def differences(values: list[int]):
    obj = Differences()
    obj.differences = values
    return obj


def scaler():
    return LocalStandardScaler()


def ewm(alpha: float = 0.9):
    obj = ExponentiallyWeightedMean()
    obj.alpha = alpha
    obj.global_ = False
    obj.groupby = None
    obj.partition_by = None
    obj.time_agg = "mean"
    return obj


def numpy_callable(name: str):
    def function():
        return None

    function.__module__ = "numpy"
    function.__name__ = name
    return function


def global_log1p_transformer():
    transformer = FunctionTransformer()
    transformer.func = numpy_callable("log1p")
    transformer.inverse_func = numpy_callable("expm1")
    transformer.validate = False
    transformer.accept_sparse = False
    transformer.check_inverse = True
    transformer.feature_names_out = None
    transformer.kw_args = None
    transformer.inv_kw_args = None

    obj = GlobalSklearnTransformer()
    obj.transformer = transformer
    return obj


def global_log1p_legacy_state():
    return {
        "transformer": {
            "class": "sklearn.preprocessing.FunctionTransformer",
            "func": "numpy.log1p",
            "inverse_func": "numpy.expm1",
            "validate": False,
            "accept_sparse": False,
            "check_inverse": True,
            "feature_names_out": None,
            "kw_args": None,
            "inv_kw_args": None,
        }
    }


def phase7_config(target_transforms, lag_transforms=None):
    return {
        "mlf_fit_params": {"static_features": []},
        "mlf_init_params": {
            "date_features": None,
            "lag_transforms": lag_transforms,
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


def test_global_log1p_legacy_repr_bridge_matches_live_config() -> None:
    frozen = phase7_config(
        [
            "<mlforecast.target_transforms.GlobalSklearnTransformer object at 0x1234>",
            "<mlforecast.target_transforms.LocalStandardScaler object at 0x5678>",
        ]
    )
    replay = phase7_config([global_log1p_transformer(), scaler()])
    legacy_states = {
        "mlforecast.target_transforms.GlobalSklearnTransformer": (global_log1p_legacy_state()),
    }

    assert canonical_semantic_sha256_v1(
        frozen, legacy_object_states=legacy_states
    ) == canonical_semantic_sha256_v1(replay)


def test_verified_lag_transform_json_key_bridge_matches_live_config() -> None:
    frozen = phase7_config(
        [differences([1]), scaler()],
        lag_transforms={"1": ["ExponentiallyWeightedMean(alpha=0.9)"]},
    )
    replay = phase7_config(
        [differences([1]), scaler()],
        lag_transforms={1: [ewm()]},
    )

    assert canonical_semantic_sha256_v1(frozen) == canonical_semantic_sha256_v1(replay)


def test_lag_transform_key_collision_fails_closed() -> None:
    config = phase7_config(
        [],
        lag_transforms={
            1: [ewm()],
            "1": ["ExponentiallyWeightedMean(alpha=0.9)"],
        },
    )

    with pytest.raises(SemanticConfigError, match="key collision"):
        canonical_semantic_sha256_v1(config)


def test_invalid_lag_transform_key_fails_closed() -> None:
    config = phase7_config(
        [],
        lag_transforms={"01": ["ExponentiallyWeightedMean(alpha=0.9)"]},
    )

    with pytest.raises(SemanticConfigError, match="positive decimal integers"):
        canonical_semantic_sha256_v1(config)


def test_non_string_mapping_key_outside_lag_transforms_fails_closed() -> None:
    with pytest.raises(SemanticConfigError, match="outside the verified"):
        canonical_semantic_sha256_v1({"other": {1: "x"}})


def test_unsupported_live_ewm_state_fails_closed() -> None:
    config = phase7_config([], lag_transforms={1: [ewm(alpha=0.8)]})

    with pytest.raises(SemanticConfigError, match="ExponentiallyWeightedMean state"):
        canonical_semantic_sha256_v1(config)


def test_unsupported_frozen_ewm_repr_fails_closed() -> None:
    config = phase7_config(
        [],
        lag_transforms={"1": ["ExponentiallyWeightedMean(alpha=0.8)"]},
    )

    with pytest.raises(SemanticConfigError, match="unsupported frozen"):
        canonical_semantic_sha256_v1(config)


def test_global_sklearn_transformer_rejects_unknown_function_state() -> None:
    transform = global_log1p_transformer()
    transform.transformer.inverse_func = numpy_callable("sqrt")

    with pytest.raises(SemanticConfigError, match="unsupported GlobalSklearnTransformer"):
        canonical_semantic_sha256_v1(phase7_config([transform, scaler()]))


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
