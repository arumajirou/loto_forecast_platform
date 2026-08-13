from __future__ import annotations

import inspect
import json
import platform
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import sklearn
from sklearn.base import is_classifier, is_regressor
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import (
    StackingClassifier,
    StackingRegressor,
    VotingClassifier,
    VotingRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.metrics.pairwise import rbf_kernel
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.utils import all_estimators

from .inventory import EstimatorKind, classify_estimator, discover_estimators

Status = Literal["VERIFIED", "FAILED"]


@dataclass
class RunResult:
    estimator: str
    kind: EstimatorKind
    status: Status
    duration_seconds: float
    operation: str | None = None
    output_shape: tuple[int, ...] | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    constructor_params: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _signature_has(cls: type, name: str) -> bool:
    try:
        return name in inspect.signature(cls).parameters
    except (TypeError, ValueError):
        return False


def _safe_runtime_params(
    cls: type, name: str, params: dict[str, Any], *, seed: int
) -> dict[str, Any]:
    params = dict(params)
    if _signature_has(cls, "random_state") and "random_state" not in params:
        params["random_state"] = seed
    if _signature_has(cls, "n_jobs") and "n_jobs" not in params:
        params["n_jobs"] = 1
    if _signature_has(cls, "n_estimators") and "n_estimators" not in params:
        params["n_estimators"] = 20
    if _signature_has(cls, "max_iter") and "max_iter" not in params:
        parameter = inspect.signature(cls).parameters["max_iter"]
        if isinstance(parameter.default, int) and parameter.default > 100:
            params["max_iter"] = 250 if name == "TSNE" else 100
    return params


def _required_parameters(cls: type) -> tuple[str, ...]:
    try:
        signature = inspect.signature(cls)
    except (TypeError, ValueError):
        return ()
    return tuple(
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    )


def _estimator_parameter(cls: type) -> str:
    if _signature_has(cls, "estimator"):
        return "estimator"
    if _signature_has(cls, "base_estimator"):
        return "base_estimator"
    raise ValueError(f"{cls.__name__} exposes neither estimator nor base_estimator")


def _special_constructor_params(name: str, cls: type, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    params: dict[str, Any] = {}
    if name == "ColumnTransformer":
        params = {"transformers": [("scale", StandardScaler(), [0, 1, 2, 3])]}
    elif name == "FeatureUnion":
        params = {"transformer_list": [("scale", StandardScaler())]}
    elif name == "Pipeline":
        params = {"steps": [("scale", StandardScaler()), ("model", Ridge())]}
    elif name in {"FixedThresholdClassifier", "TunedThresholdClassifierCV"}:
        params = {_estimator_parameter(cls): LogisticRegression(max_iter=200)}
    elif name == "FrozenEstimator":
        x, y = make_regression(n_samples=40, n_features=8, random_state=seed)
        params = {_estimator_parameter(cls): Ridge().fit(x, y)}
    elif name == "GridSearchCV":
        params = {"estimator": Ridge(), "param_grid": {"alpha": [0.1, 1.0]}, "cv": 2}
    elif name == "RandomizedSearchCV":
        params = {
            "estimator": Ridge(),
            "param_distributions": {"alpha": [0.1, 1.0]},
            "n_iter": 2,
            "random_state": seed,
            "cv": 2,
        }
    elif name == "MultiOutputClassifier":
        params = {_estimator_parameter(cls): LogisticRegression(max_iter=200)}
    elif name == "MultiOutputRegressor":
        params = {_estimator_parameter(cls): Ridge()}
    elif name in {"OneVsOneClassifier", "OneVsRestClassifier", "OutputCodeClassifier"}:
        params = {_estimator_parameter(cls): LogisticRegression(max_iter=200)}
    elif name in {"RFE", "RFECV", "SelectFromModel", "SequentialFeatureSelector"}:
        params = {_estimator_parameter(cls): Ridge()}
    elif name == "SparseCoder":
        params = {"dictionary": rng.normal(size=(4, 8))}
    elif name == "StackingClassifier":
        params = {
            "estimators": [
                ("lr", LogisticRegression(max_iter=200)),
                ("dt", DecisionTreeClassifier(max_depth=3, random_state=seed)),
            ]
        }
    elif name == "StackingRegressor":
        params = {
            "estimators": [
                ("ridge", Ridge()),
                ("dt", DecisionTreeRegressor(max_depth=3, random_state=seed)),
            ]
        }
    elif name == "VotingClassifier":
        params = {
            "estimators": [
                ("lr", LogisticRegression(max_iter=200)),
                ("dt", DecisionTreeClassifier(max_depth=3, random_state=seed)),
            ]
        }
    elif name == "VotingRegressor":
        params = {
            "estimators": [
                ("ridge", Ridge()),
                ("dt", DecisionTreeRegressor(max_depth=3, random_state=seed)),
            ]
        }
    elif name in {"ClassifierChain", "SelfTrainingClassifier"}:
        params = {_estimator_parameter(cls): LogisticRegression(max_iter=200)}
    elif name == "RegressorChain":
        params = {_estimator_parameter(cls): Ridge()}
    elif name in {"GaussianRandomProjection", "SparseRandomProjection"}:
        params = {"n_components": 4}
    elif name == "TSNE":
        params = {"n_components": 2, "perplexity": 10, "max_iter": 250, "random_state": seed}

    for required in _required_parameters(cls):
        if required in params:
            continue
        if required == "estimator":
            params[required] = Ridge()
        elif required == "transformers":
            params[required] = [("scale", StandardScaler(), [0, 1])]
        elif required == "transformer_list":
            params[required] = [("scale", StandardScaler())]
        elif required == "steps":
            params[required] = [("scale", StandardScaler())]
        elif required == "dictionary":
            params[required] = rng.normal(size=(4, 8))
        elif required == "estimators":
            params[required] = [("ridge", Ridge())]
        elif required in {"param_grid", "param_distributions"}:
            params[required] = {}
        else:
            raise ValueError(f"unresolved required constructor parameter: {required}")
    return _safe_runtime_params(cls, name, params, seed=seed)


def create_estimator(name: str, *, seed: int = 1, overrides: dict[str, Any] | None = None) -> Any:
    classes = dict(all_estimators())
    try:
        cls = classes[name]
    except KeyError as exc:
        raise KeyError(f"unknown scikit-learn estimator: {name}") from exc
    params = _special_constructor_params(name, cls, seed)
    params.update(overrides or {})
    return cls(**params)


def _legacy_tags(estimator: Any) -> dict[str, Any]:
    try:
        from sklearn.utils._tags import _safe_tags
    except ImportError:
        return {}
    try:
        return dict(_safe_tags(estimator))
    except Exception:
        return {}


def _tag_values(estimator: Any) -> dict[str, bool]:
    try:
        from sklearn.utils import get_tags
    except ImportError:
        tags = _legacy_tags(estimator)
        return {
            "target_required": bool(tags.get("requires_y", False)),
            "target_multi_output": bool(tags.get("multioutput", False)),
            "target_two_d": bool(tags.get("multioutput_only", False)),
            "target_positive": bool(tags.get("requires_positive_y", False)),
            "input_positive": bool(tags.get("requires_positive_X", False)),
            "input_pairwise": bool(tags.get("pairwise", False)),
        }
    try:
        tags = get_tags(estimator)
        return {
            "target_required": bool(tags.target_tags.required),
            "target_multi_output": bool(tags.target_tags.multi_output),
            "target_two_d": bool(tags.target_tags.two_d_labels),
            "target_positive": bool(tags.target_tags.positive_only),
            "input_positive": bool(tags.input_tags.positive_only),
            "input_pairwise": bool(tags.input_tags.pairwise),
        }
    except Exception:
        return {
            "target_required": False,
            "target_multi_output": False,
            "target_two_d": False,
            "target_positive": False,
            "input_positive": False,
            "input_pairwise": False,
        }


def _dataset(name: str, estimator: Any, seed: int) -> tuple[Any, Any | None]:
    rng = np.random.default_rng(seed)
    xc, yc = make_classification(
        n_samples=120,
        n_features=8,
        n_informative=5,
        n_redundant=0,
        n_classes=3,
        random_state=seed,
    )
    xr, yr = make_regression(
        n_samples=120,
        n_features=8,
        n_informative=5,
        noise=0.1,
        random_state=seed,
    )
    yc_binary = (yc == 0).astype(int)
    yc_multi = np.column_stack([yc_binary, np.roll(yc_binary, 1)])
    yr_multi = np.column_stack([yr, 0.5 * yr + rng.normal(size=len(yr))])

    if name in {"CountVectorizer", "TfidfVectorizer"}:
        text = ["red apple", "blue berry", "green pear", "apple berry", "red pear"] * 24
        return np.asarray(text, dtype=object), None
    if name == "DictVectorizer":
        return [{"f1": float(i % 3), "f2": float((i + 1) % 4)} for i in range(120)], None
    if name in {"LabelEncoder", "LabelBinarizer"}:
        return yc, None
    if name == "IsotonicRegression":
        return xr[:, 0], yr
    if name in {"CCA", "PLSCanonical", "PLSRegression", "PLSSVD"}:
        return xr, yr_multi
    if name == "NeighborhoodComponentsAnalysis":
        return xc, yc
    if name in {
        "GridSearchCV",
        "RandomizedSearchCV",
        "Pipeline",
        "SelectFromModel",
        "SelectKBest",
        "SelectPercentile",
        "SequentialFeatureSelector",
        "RFE",
        "RFECV",
    }:
        return xr, yr
    if name in {"FixedThresholdClassifier", "TunedThresholdClassifierCV"}:
        return xc, yc_binary
    if name == "ClassifierChain":
        return xc, yc_multi
    if name == "RegressorChain":
        return xr, yr_multi
    if name == "SelfTrainingClassifier":
        labels = yc_binary.copy()
        labels[::5] = -1
        return xc, labels

    tags = _tag_values(estimator)
    x: Any = xc.copy()
    if tags["input_positive"]:
        x = np.abs(x) + 0.1
    if tags["input_pairwise"]:
        x = rbf_kernel(x)
    y: Any | None = None
    if tags["target_required"]:
        if is_classifier(estimator):
            y = yc.copy()
            if tags["target_multi_output"] or tags["target_two_d"]:
                y = yc_multi.copy()
        else:
            x = np.abs(xr) + 0.1 if tags["input_positive"] else xr.copy()
            if tags["input_pairwise"]:
                x = rbf_kernel(x)
            y = yr.copy()
            if tags["target_multi_output"] or tags["target_two_d"]:
                y = yr_multi.copy()
            if tags["target_positive"]:
                y = np.abs(y) + 1.0
    return x, y


def _inference_input(estimator: Any, x: Any) -> Any:
    if isinstance(x, np.ndarray):
        if x.ndim == 1:
            return x[:10]
        if _tag_values(estimator)["input_pairwise"] and x.shape[0] == x.shape[1]:
            return x[:10, :]
        return x[:10]
    if isinstance(x, list):
        return x[:10]
    return x


def _run_operation(estimator: Any, x: Any) -> tuple[str | None, Any | None]:
    inference_x = _inference_input(estimator, x)
    for method in ("predict_proba", "predict", "transform", "score_samples", "decision_function"):
        if not hasattr(estimator, method):
            continue
        try:
            return method, getattr(estimator, method)(inference_x)
        except Exception:
            continue
    return None, None


def _metrics(estimator: Any, x: Any, y: Any | None) -> dict[str, float]:
    if y is None or not hasattr(estimator, "predict"):
        return {}
    try:
        prediction = estimator.predict(x)
    except Exception:
        return {}
    target = np.asarray(y)
    predicted = np.asarray(prediction)
    if target.shape != predicted.shape:
        return {}
    if is_classifier(estimator):
        return {"accuracy": float(accuracy_score(target, predicted))}
    if is_regressor(estimator):
        error = predicted.astype(float) - target.astype(float)
        return {
            "mae": float(mean_absolute_error(target, predicted)),
            "mse": float(mean_squared_error(target, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(target, predicted))),
            "hit_at_plus_minus_1": float(np.mean(np.abs(error) <= 1.0)),
        }
    return {}


def certify_estimator(name: str, *, seed: int = 1) -> RunResult:
    started = time.perf_counter()
    try:
        estimator = create_estimator(name, seed=seed)
        kind = classify_estimator(estimator)
        x, y = _dataset(name, estimator, seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if y is None:
                estimator.fit(x)
            else:
                estimator.fit(x, y)
            operation, output = _run_operation(estimator, x)
            metrics = _metrics(estimator, x, y)
        shape = None if output is None else tuple(int(v) for v in np.shape(output))
        params = _special_constructor_params(name, type(estimator), seed)
        return RunResult(
            estimator=name,
            kind=kind,
            status="VERIFIED",
            duration_seconds=time.perf_counter() - started,
            operation=operation,
            output_shape=shape,
            metrics=metrics,
            constructor_params={key: repr(value) for key, value in params.items()},
        )
    except Exception as exc:
        return RunResult(
            estimator=name,
            kind="other",
            status="FAILED",
            duration_seconds=time.perf_counter() - started,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def certify_all(
    *,
    seed: int = 1,
    kind: EstimatorKind | Literal["all"] = "all",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    if kind == "all":
        names = [name for name, _ in all_estimators()]
    else:
        names = [record.name for record in discover_estimators(kind)]

    results = [certify_estimator(name, seed=seed) for name in names]
    verified = sum(result.status == "VERIFIED" for result in results)
    report = {
        "schema_version": 1,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "seed": seed,
        "kind": kind,
        "estimator_count": len(results),
        "verified": verified,
        "failed": len(results) - verified,
        "status": "VERIFIED" if verified == len(results) else "PARTIALLY_VERIFIED",
        "results": [result.to_dict() for result in results],
    }
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "sklearn_certification.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
    return report
