"""Pinned source inventory for Darts Expanded v2 Phase 2.

This module is import-free with respect to the optional Darts runtime. It owns the
versioned Darts 0.46.1 public forecasting export fixture, classifies explicit
source exclusions, and produces the manifest hash consumed by Expanded v2.
Runtime/routing evidence is tracked separately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

DARTS_TARGET_VERSION = "0.46.1"
DARTS_BROAD_V1_ID = "darts-ensemble"

PUBLIC_FORECASTING_EXPORTS_0_46_1: tuple[str, ...] = (
    "ARIMA",
    "NaiveDrift",
    "NaiveMean",
    "NaiveMovingAverage",
    "NaiveSeasonal",
    "NaiveEnsembleModel",
    "ConformalNaiveModel",
    "ConformalQRModel",
    "EnsembleModel",
    "ExponentialSmoothing",
    "FFT",
    "KalmanForecaster",
    "LinearRegressionModel",
    "RandomForest",
    "RandomForestModel",
    "MultivariateModel",
    "RegressionEnsembleModel",
    "RegressionModel",
    "SKLearnClassifierModel",
    "SKLearnModel",
    "FourTheta",
    "Theta",
    "VARIMA",
    "LightGBMModel",
    "LightGBMClassifierModel",
    "BlockRNNModel",
    "DLinearModel",
    "GlobalNaiveAggregate",
    "GlobalNaiveDrift",
    "GlobalNaiveSeasonal",
    "NBEATSModel",
    "NHiTSModel",
    "NLinearModel",
    "RNNModel",
    "TCNModel",
    "TFTModel",
    "TiDEModel",
    "TransformerModel",
    "TSMixerModel",
    "Chronos2Model",
    "PatchTSTFMModel",
    "TimesFM2p5Model",
    "TiRexModel",
    "NeuralForecastModel",
    "Prophet",
    "CatBoostModel",
    "CatBoostClassifierModel",
    "AutoARIMA",
    "AutoCES",
    "AutoETS",
    "AutoMFLES",
    "AutoTBATS",
    "AutoTheta",
    "Croston",
    "StatsForecastModel",
    "TBATS",
    "XGBModel",
    "XGBClassifierModel",
)

DartsExclusionKind = Literal["ABSTRACT_BASE", "DEPRECATED_ALIAS"]


@dataclass(frozen=True, slots=True)
class DartsSourceExclusion:
    public_name: str
    kind: DartsExclusionKind
    replacement: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class DartsSourceIdentity:
    public_name: str
    family: str


DARTS_SOURCE_EXCLUSIONS: tuple[DartsSourceExclusion, ...] = (
    DartsSourceExclusion(
        public_name="EnsembleModel",
        kind="ABSTRACT_BASE",
        replacement=None,
        reason=("abstract ensemble base; concrete ensemble implementations are tracked separately"),
    ),
    DartsSourceExclusion(
        public_name="RandomForest",
        kind="DEPRECATED_ALIAS",
        replacement="RandomForestModel",
        reason="deprecated public alias of RandomForestModel",
    ),
    DartsSourceExclusion(
        public_name="RegressionModel",
        kind="DEPRECATED_ALIAS",
        replacement="SKLearnModel",
        reason="deprecated public alias superseded by SKLearnModel",
    ),
)

_CLASSIFIERS = frozenset(
    {
        "SKLearnClassifierModel",
        "LightGBMClassifierModel",
        "CatBoostClassifierModel",
        "XGBClassifierModel",
    }
)
_ENSEMBLES = frozenset({"NaiveEnsembleModel", "RegressionEnsembleModel"})
_CONFORMAL = frozenset({"ConformalNaiveModel", "ConformalQRModel"})
_FOUNDATION = frozenset({"Chronos2Model", "PatchTSTFMModel", "TimesFM2p5Model", "TiRexModel"})
_REGRESSION = frozenset(
    {
        "LinearRegressionModel",
        "RandomForestModel",
        "SKLearnModel",
        "LightGBMModel",
        "CatBoostModel",
        "XGBModel",
    }
)
_TORCH = frozenset(
    {
        "BlockRNNModel",
        "DLinearModel",
        "NBEATSModel",
        "NHiTSModel",
        "NLinearModel",
        "RNNModel",
        "TCNModel",
        "TFTModel",
        "TiDEModel",
        "TransformerModel",
        "TSMixerModel",
        "NeuralForecastModel",
    }
)
_GLOBAL = frozenset({"GlobalNaiveAggregate", "GlobalNaiveDrift", "GlobalNaiveSeasonal"})
_WRAPPERS = frozenset({"StatsForecastModel"})


def _family(public_name: str) -> str:
    if public_name in _CLASSIFIERS:
        return "classifier"
    if public_name in _ENSEMBLES:
        return "ensemble"
    if public_name in _CONFORMAL:
        return "conformal"
    if public_name in _FOUNDATION:
        return "foundation"
    if public_name in _REGRESSION:
        return "regression"
    if public_name in _TORCH:
        return "torch"
    if public_name in _GLOBAL:
        return "global"
    if public_name in _WRAPPERS:
        return "wrapper"
    return "forecasting"


def darts_source_identities() -> tuple[DartsSourceIdentity, ...]:
    """Return deterministic Darts source identities after explicit exclusions."""

    excluded = {row.public_name for row in DARTS_SOURCE_EXCLUSIONS}
    rows = tuple(
        DartsSourceIdentity(public_name=name, family=_family(name))
        for name in PUBLIC_FORECASTING_EXPORTS_0_46_1
        if name not in excluded
    )
    names = [row.public_name for row in rows]
    if len(names) != len(set(names)):
        raise AssertionError("duplicate Darts source implementation names")
    return rows


def darts_source_manifest() -> dict[str, object]:
    """Return the canonical source-classification payload used for hashing."""

    identities = darts_source_identities()
    return {
        "darts_version": DARTS_TARGET_VERSION,
        "public_exports": list(PUBLIC_FORECASTING_EXPORTS_0_46_1),
        "exclusions": [asdict(row) for row in DARTS_SOURCE_EXCLUSIONS],
        "implementation_names": [row.public_name for row in identities],
        "implementation_count": len(identities),
    }


def darts_source_manifest_sha256() -> str:
    payload = json.dumps(
        darts_source_manifest(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
