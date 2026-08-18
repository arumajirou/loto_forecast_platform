from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any, TypeAlias

JSONPrimitive: TypeAlias = None | bool | int | float | str
CanonicalValue: TypeAlias = JSONPrimitive | list["CanonicalValue"] | dict[str, "CanonicalValue"]
SemanticPath: TypeAlias = tuple[str | int, ...]

SEMANTIC_CONFIG_SCHEMA_V1 = "loto.semantic-config/v1"

_LEGACY_OBJECT_RE = re.compile(
    r"^<(?P<class_path>[A-Za-z_][A-Za-z0-9_.]*) object at 0x[0-9A-Fa-f]+>$"
)
_POSITIVE_DECIMAL_KEY_RE = re.compile(r"^[1-9][0-9]*$")
_GLOBAL_SKLEARN_TRANSFORMER = "mlforecast.target_transforms.GlobalSklearnTransformer"
_FUNCTION_TRANSFORMER_CLASS = "sklearn.preprocessing.FunctionTransformer"
_EXPONENTIALLY_WEIGHTED_MEAN = "mlforecast.lag_transforms.ExponentiallyWeightedMean"
_LAG_TRANSFORMS_PATH: SemanticPath = ("mlf_init_params", "lag_transforms")


class SemanticConfigError(TypeError):
    """Raised when semantic config cannot be canonicalized without information loss."""


def _class_path(value: object) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _canonical_float(value: float) -> float:
    if not math.isfinite(value):
        raise SemanticConfigError("semantic config cannot contain NaN or infinity")
    if value == 0.0:
        return 0.0
    return value


def _callable_path(value: object) -> str | None:
    if value is None:
        return None

    name = getattr(value, "__name__", None)
    module = getattr(value, "__module__", None)
    if isinstance(module, str) and module and isinstance(name, str) and name:
        return f"{module}.{name}"

    if _class_path(value) == "numpy.ufunc" and isinstance(name, str) and name:
        return f"numpy.{name}"

    return None


def _canonical_global_sklearn_transformer(value: object) -> dict[str, CanonicalValue]:
    transformer = getattr(value, "transformer", None)
    if transformer is None:
        raise SemanticConfigError(
            "GlobalSklearnTransformer is missing constructor state: transformer"
        )

    transformer_class = _class_path(transformer)
    if transformer_class != "sklearn.preprocessing._function_transformer.FunctionTransformer":
        raise SemanticConfigError(
            f"unsupported GlobalSklearnTransformer transformer: {transformer_class}"
        )

    state = {
        "class": _FUNCTION_TRANSFORMER_CLASS,
        "func": _callable_path(getattr(transformer, "func", None)),
        "inverse_func": _callable_path(getattr(transformer, "inverse_func", None)),
        "validate": getattr(transformer, "validate", None),
        "accept_sparse": getattr(transformer, "accept_sparse", None),
        "check_inverse": getattr(transformer, "check_inverse", None),
        "feature_names_out": getattr(transformer, "feature_names_out", None),
        "kw_args": getattr(transformer, "kw_args", None),
        "inv_kw_args": getattr(transformer, "inv_kw_args", None),
    }

    expected = {
        "class": _FUNCTION_TRANSFORMER_CLASS,
        "func": "numpy.log1p",
        "inverse_func": "numpy.expm1",
        "validate": False,
        "accept_sparse": False,
        "check_inverse": True,
        "feature_names_out": None,
        "kw_args": None,
        "inv_kw_args": None,
    }
    if state != expected:
        raise SemanticConfigError(
            f"unsupported GlobalSklearnTransformer FunctionTransformer state: {state!r}"
        )

    return {
        "__python_object_class__": _GLOBAL_SKLEARN_TRANSFORMER,
        "state": {"transformer": expected},
    }


def _canonical_mlforecast_target_transform(
    value: object, class_path: str
) -> dict[str, CanonicalValue]:
    if class_path == "mlforecast.target_transforms.Differences":
        differences = getattr(value, "differences", None)
        if differences is None:
            raise SemanticConfigError(
                "MLForecast Differences is missing constructor state: differences"
            )
        try:
            normalized = [int(item) for item in differences]
        except (TypeError, ValueError) as exc:
            raise SemanticConfigError(
                "MLForecast Differences contains invalid differences"
            ) from exc
        return {
            "__python_object_class__": class_path,
            "state": {"differences": normalized},
        }

    if class_path == "mlforecast.target_transforms.LocalStandardScaler":
        return {
            "__python_object_class__": class_path,
            "state": {},
        }

    if class_path == _GLOBAL_SKLEARN_TRANSFORMER:
        return _canonical_global_sklearn_transformer(value)

    raise SemanticConfigError(f"unsupported MLForecast target transform: {class_path}")


def _canonical_ewm_state(alpha: float) -> dict[str, CanonicalValue]:
    normalized_alpha = _canonical_float(alpha)
    if normalized_alpha != 0.9:
        raise SemanticConfigError(
            "unsupported MLForecast ExponentiallyWeightedMean alpha: "
            f"{normalized_alpha!r}; expected 0.9"
        )
    return {
        "__python_object_class__": _EXPONENTIALLY_WEIGHTED_MEAN,
        "state": {
            "alpha": normalized_alpha,
            "global_": False,
            "groupby": None,
            "partition_by": None,
            "time_agg": "mean",
        },
    }


def _canonical_mlforecast_lag_transform(
    value: object, class_path: str
) -> dict[str, CanonicalValue]:
    if class_path != _EXPONENTIALLY_WEIGHTED_MEAN:
        raise SemanticConfigError(f"unsupported MLForecast lag transform: {class_path}")

    state = {
        "alpha": getattr(value, "alpha", None),
        "global_": getattr(value, "global_", None),
        "groupby": getattr(value, "groupby", None),
        "partition_by": getattr(value, "partition_by", None),
        "time_agg": getattr(value, "time_agg", None),
    }
    expected = {
        "alpha": 0.9,
        "global_": False,
        "groupby": None,
        "partition_by": None,
        "time_agg": "mean",
    }
    if state != expected:
        raise SemanticConfigError(
            "unsupported MLForecast ExponentiallyWeightedMean state: "
            f"{state!r}; expected {expected!r}"
        )
    return _canonical_ewm_state(float(state["alpha"]))


def _canonical_legacy_lag_transform_repr(value: str) -> dict[str, CanonicalValue] | None:
    if value == "ExponentiallyWeightedMean(alpha=0.9)":
        return _canonical_ewm_state(0.9)
    if value.startswith("ExponentiallyWeightedMean("):
        raise SemanticConfigError(
            f"unsupported frozen MLForecast ExponentiallyWeightedMean repr: {value!r}"
        )
    return None


def _canonical_legacy_object_repr(
    value: str,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, CanonicalValue] | None:
    match = _LEGACY_OBJECT_RE.fullmatch(value)
    if match is None:
        return None

    class_path = match.group("class_path")
    if class_path == "mlforecast.target_transforms.LocalStandardScaler":
        state: Mapping[str, Any] = {}
    else:
        if legacy_object_states is None or class_path not in legacy_object_states:
            raise SemanticConfigError(
                "legacy object repr lost constructor state; explicit state is required for "
                f"{class_path}"
            )
        state = legacy_object_states[class_path]

    return {
        "__python_object_class__": class_path,
        "state": canonicalize_semantic_value(
            dict(state), legacy_object_states=legacy_object_states
        ),
    }


def _is_within_lag_transforms(path: SemanticPath) -> bool:
    return path[: len(_LAG_TRANSFORMS_PATH)] == _LAG_TRANSFORMS_PATH


def _normalize_lag_key(key: object) -> int:
    if isinstance(key, bool):
        raise SemanticConfigError("MLForecast lag transform keys cannot be bool")
    if isinstance(key, int):
        lag = key
    elif isinstance(key, str) and _POSITIVE_DECIMAL_KEY_RE.fullmatch(key):
        lag = int(key)
    else:
        raise SemanticConfigError(
            "MLForecast lag transform keys must be positive decimal integers or their "
            f"JSON string form, got {key!r} ({type(key).__name__})"
        )
    if lag <= 0:
        raise SemanticConfigError(f"MLForecast lag transform key must be > 0, got {lag}")
    return lag


def _canonical_lag_transform_mapping(
    value: Mapping[Any, Any],
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None,
    path: SemanticPath,
) -> dict[str, CanonicalValue]:
    normalized: dict[int, Any] = {}
    original_keys: dict[int, object] = {}
    for key, item in value.items():
        lag = _normalize_lag_key(key)
        if lag in normalized:
            raise SemanticConfigError(
                "MLForecast lag transform key collision after JSON normalization: "
                f"{original_keys[lag]!r} and {key!r} both map to lag {lag}"
            )
        normalized[lag] = item
        original_keys[lag] = key

    entries: list[CanonicalValue] = []
    for lag in sorted(normalized):
        entries.append(
            {
                "lag": lag,
                "transforms": _canonicalize_semantic_value(
                    normalized[lag],
                    legacy_object_states=legacy_object_states,
                    path=path + (lag,),
                ),
            }
        )
    return {"__mlforecast_lag_transforms__": entries}


def _canonicalize_semantic_value(
    value: Any,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None,
    path: SemanticPath,
) -> CanonicalValue:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, str):
        if _is_within_lag_transforms(path):
            legacy_lag = _canonical_legacy_lag_transform_repr(value)
            if legacy_lag is not None:
                return legacy_lag
        legacy = _canonical_legacy_object_repr(value, legacy_object_states=legacy_object_states)
        return value if legacy is None else legacy

    if isinstance(value, Mapping):
        if path == _LAG_TRANSFORMS_PATH:
            return _canonical_lag_transform_mapping(
                value,
                legacy_object_states=legacy_object_states,
                path=path,
            )

        result: dict[str, CanonicalValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SemanticConfigError(
                    "semantic config mapping keys must be strings outside the verified "
                    f"MLForecast lag_transforms path, got {type(key).__name__} at {path!r}"
                )
            result[key] = _canonicalize_semantic_value(
                item,
                legacy_object_states=legacy_object_states,
                path=path + (key,),
            )
        return result

    if isinstance(value, list):
        return [
            _canonicalize_semantic_value(
                item,
                legacy_object_states=legacy_object_states,
                path=path + (index,),
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, tuple):
        return {
            "__tuple__": [
                _canonicalize_semantic_value(
                    item,
                    legacy_object_states=legacy_object_states,
                    path=path + (index,),
                )
                for index, item in enumerate(value)
            ]
        }

    if isinstance(value, range):
        return {
            "__range__": {
                "start": value.start,
                "stop": value.stop,
                "step": value.step,
            }
        }

    class_path = _class_path(value)
    if class_path.startswith("mlforecast.target_transforms."):
        return _canonical_mlforecast_target_transform(value, class_path)
    if class_path.startswith("mlforecast.lag_transforms."):
        if not _is_within_lag_transforms(path):
            raise SemanticConfigError(
                f"MLForecast lag transform found outside lag_transforms path: {path!r}"
            )
        return _canonical_mlforecast_lag_transform(value, class_path)

    # NumPy scalar support without importing NumPy as a hard dependency.
    if class_path.startswith("numpy.") and hasattr(value, "item"):
        return _canonicalize_semantic_value(
            value.item(),
            legacy_object_states=legacy_object_states,
            path=path,
        )

    raise SemanticConfigError(
        f"unsupported semantic config type: {class_path}; add an explicit adapter"
    )


def canonicalize_semantic_value(
    value: Any,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None = None,
) -> CanonicalValue:
    """Convert supported config values to deterministic, loss-aware JSON values.

    Unsupported objects fail closed instead of falling back to ``str(value)``.
    Legacy ``<module.Class object at 0x...>`` strings are accepted only when
    constructor state can be reconstructed explicitly. The only non-string
    mapping-key bridge is the verified MLForecast ``mlf_init_params.lag_transforms``
    path, where JSON string keys and live positive integer lag keys are normalized
    to an explicit tagged representation with collision checks.
    """

    return _canonicalize_semantic_value(
        value,
        legacy_object_states=legacy_object_states,
        path=(),
    )


def canonical_semantic_document_v1(
    config: Any,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, CanonicalValue]:
    return {
        "schema": SEMANTIC_CONFIG_SCHEMA_V1,
        "config": canonicalize_semantic_value(config, legacy_object_states=legacy_object_states),
    }


def canonical_semantic_bytes_v1(
    config: Any,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None = None,
) -> bytes:
    document = canonical_semantic_document_v1(config, legacy_object_states=legacy_object_states)
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_semantic_sha256_v1(
    config: Any,
    *,
    legacy_object_states: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    return hashlib.sha256(
        canonical_semantic_bytes_v1(config, legacy_object_states=legacy_object_states)
    ).hexdigest()
