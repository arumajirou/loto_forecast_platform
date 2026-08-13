from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from typing import Literal

from sklearn.base import is_classifier, is_regressor
from sklearn.utils import all_estimators

EstimatorKind = Literal["classifier", "regressor", "cluster", "transformer", "other"]


@dataclass(frozen=True)
class EstimatorRecord:
    name: str
    kind: EstimatorKind
    module: str
    class_name: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _is_clusterer(estimator: object) -> bool:
    try:
        from sklearn.base import is_clusterer
    except ImportError:
        return getattr(estimator, "_estimator_type", None) == "clusterer"
    return bool(is_clusterer(estimator))


def classify_estimator(estimator: object) -> EstimatorKind:
    if is_classifier(estimator):
        return "classifier"
    if is_regressor(estimator):
        return "regressor"
    if _is_clusterer(estimator):
        return "cluster"
    if hasattr(estimator, "transform") or hasattr(estimator, "fit_transform"):
        return "transformer"
    return "other"


def discover_estimators(kind: EstimatorKind | Literal["all"] = "all") -> tuple[EstimatorRecord, ...]:
    records: list[EstimatorRecord] = []
    classifier_names = {name for name, _ in all_estimators(type_filter="classifier")}
    regressor_names = {name for name, _ in all_estimators(type_filter="regressor")}
    cluster_names = {name for name, _ in all_estimators(type_filter="cluster")}
    transformer_names = {name for name, _ in all_estimators(type_filter="transformer")}
    for name, estimator_class in all_estimators():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                estimator = estimator_class()
                estimator_kind = classify_estimator(estimator)
        except Exception:
            estimator_kind = "other"
            if name in classifier_names:
                estimator_kind = "classifier"
            elif name in regressor_names:
                estimator_kind = "regressor"
            elif name in cluster_names:
                estimator_kind = "cluster"
            elif name in transformer_names:
                estimator_kind = "transformer"
        if kind != "all" and estimator_kind != kind:
            continue
        records.append(
            EstimatorRecord(
                name=name,
                kind=estimator_kind,
                module=estimator_class.__module__,
                class_name=estimator_class.__name__,
            )
        )
    return tuple(records)
