"""Complete model registry, built programmatically from primary-source name lists.

Constitution principle I: counts are *computed*, never typed. Every list below is a verbatim
transcription of an upstream ``__all__`` at the recorded revision, so a drift between this
file and upstream is detectable by re-reading the upstream ``__all__``.

Primary sources (retrieved 2026-07-30):

* ``neuralforecast/models/__init__.py``  -> :data:`NEURALFORECAST_MODELS`      (37)
* ``neuralforecast/auto.py``             -> :data:`NEURALFORECAST_AUTOMODELS`   (36)
* ``statsforecast/models.py``            -> :data:`STATSFORECAST_MODELS`        (41)
* ``mlforecast/auto.py``                 -> :data:`MLFORECAST_AUTOMODELS`       (8)
* ``hierarchicalforecast/methods.py``    -> :data:`RECONCILIATION_METHODS`      (10)
* ``huggingface.co/models?pipeline_tag=time-series-forecasting`` -> :data:`TSFM_MODELS`

TSFM entries carry ``repo_id`` but ``revision=None``. A ``None`` revision is deliberately
*not* filled with a plausible-looking SHA: an unverified commit hash is worse than an
explicit gap, because it makes ``protocol_hash`` look reproducible when it is not. Run
``loto models pin`` against a network-enabled environment to resolve them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "ModelEntry",
    "NEURALFORECAST_MODELS",
    "NEURALFORECAST_AUTOMODELS",
    "STATSFORECAST_MODELS",
    "MLFORECAST_AUTOMODELS",
    "RECONCILIATION_METHODS",
    "TSFM_MODELS",
    "build_catalog",
    "catalog_counts",
    "catalog_by_library",
    "PRIMARY_SOURCES",
]

Task = Literal["candidate", "position", "position_series", "candidate_series", "foundation", "reconciliation"]

PRIMARY_SOURCES: dict[str, str] = {
    "neuralforecast": "github.com/Nixtla/neuralforecast @ main:neuralforecast/models/__init__.py",
    "neuralforecast_auto": "github.com/Nixtla/neuralforecast @ main:neuralforecast/auto.py",
    "statsforecast": "github.com/Nixtla/statsforecast @ main:python/statsforecast/models.py",
    "mlforecast_auto": "github.com/Nixtla/mlforecast @ main:mlforecast/auto.py",
    "hierarchicalforecast": "github.com/Nixtla/hierarchicalforecast @ main:hierarchicalforecast/methods.py",
    "tsfm": "huggingface.co/models?pipeline_tag=time-series-forecasting (2026-07-30)",
}


@dataclass(frozen=True)
class ModelEntry:
    """One row of the registry."""

    model_id: str
    family: str
    library: str
    task: Task
    class_name: str
    priority: str = "p1"
    package: str | None = None
    capabilities: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    repo_id: str | None = None
    revision: str | None = None
    license: str | None = None
    notes: str = ""
    supports_exogenous: bool = False
    supports_probabilistic: bool = False
    multivariate: bool = False
    requires_n_series: bool = False

    @property
    def revision_status(self) -> str:
        if self.repo_id is None:
            return "NOT_APPLICABLE"
        return "PINNED" if self.revision else "UNPINNED"

    def to_row(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "family": self.family,
            "library": self.library,
            "task": self.task,
            "class_name": self.class_name,
            "priority": self.priority,
            "package": self.package or "",
            "capabilities": ",".join(self.capabilities),
            "default_params": self.default_params,
            "repo_id": self.repo_id or "",
            "revision": self.revision or "",
            "revision_status": self.revision_status,
            "license": self.license or "",
            "supports_exogenous": self.supports_exogenous,
            "supports_probabilistic": self.supports_probabilistic,
            "multivariate": self.multivariate,
            "requires_n_series": self.requires_n_series,
            "primary_source": PRIMARY_SOURCES.get(self.library, ""),
            "notes": self.notes,
        }


# --------------------------------------------------------------------------------------
# Primary-source name lists -- verbatim transcriptions of upstream ``__all__``
# --------------------------------------------------------------------------------------

#: ``neuralforecast.models.__all__``
NEURALFORECAST_MODELS: tuple[str, ...] = (
    "RNN", "GRU", "LSTM", "TCN", "DeepAR", "DilatedRNN", "MLP", "NHITS", "NBEATS",
    "NBEATSx", "DLinear", "NLinear", "TFT", "VanillaTransformer", "Informer",
    "Autoformer", "PatchTST", "FEDformer", "StemGNN", "HINT", "TimesNet", "TimeLLM",
    "TSMixer", "TSMixerx", "MLPMultivariate", "iTransformer", "BiTCN", "TiDE",
    "DeepNPTS", "SOFTS", "SOFTSSharp", "TimeMixer", "KAN", "RMoK", "TimeXer",
    "xLSTM", "XLinear",
)

#: ``neuralforecast.auto.__all__`` minus the two option containers
NEURALFORECAST_AUTOMODELS: tuple[str, ...] = (
    "AutoRNN", "AutoLSTM", "AutoGRU", "AutoTCN", "AutoDeepAR", "AutoDilatedRNN",
    "AutoBiTCN", "AutoxLSTM", "AutoMLP", "AutoNBEATS", "AutoNBEATSx", "AutoNHITS",
    "AutoDLinear", "AutoNLinear", "AutoTiDE", "AutoDeepNPTS", "AutoKAN", "AutoTFT",
    "AutoVanillaTransformer", "AutoInformer", "AutoAutoformer", "AutoFEDformer",
    "AutoPatchTST", "AutoiTransformer", "AutoTimeXer", "AutoTimesNet", "AutoStemGNN",
    "AutoHINT", "AutoTSMixer", "AutoTSMixerx", "AutoMLPMultivariate", "AutoSOFTS",
    "AutoSOFTSSharp", "AutoTimeMixer", "AutoRMoK", "AutoXLinear",
)

#: ``statsforecast.models.__all__``
STATSFORECAST_MODELS: tuple[str, ...] = (
    "AutoARIMA", "AutoETS", "AutoCES", "AutoTheta", "AutoMFLES", "AutoTBATS", "ARIMA",
    "AutoRegressive", "SimpleExponentialSmoothing", "SimpleExponentialSmoothingOptimized",
    "SeasonalExponentialSmoothing", "SeasonalExponentialSmoothingOptimized", "Holt",
    "HoltWinters", "HistoricAverage", "Naive", "RandomWalkWithDrift", "SeasonalNaive",
    "ConformalSeasonalPool", "WindowAverage", "SeasonalWindowAverage", "ADIDA",
    "CrostonClassic", "CrostonOptimized", "CrostonSBA", "IMAPA", "TSB", "MSTL", "MFLES",
    "TBATS", "Theta", "OptimizedTheta", "DynamicTheta", "DynamicOptimizedTheta", "GARCH",
    "ARCH", "SklearnModel", "ConstantModel", "ZeroModel", "NaNModel", "UCM",
)

#: ``mlforecast.auto.__all__`` -- the Auto* estimators only
MLFORECAST_AUTOMODELS: tuple[str, ...] = (
    "AutoLightGBM", "AutoXGBoost", "AutoCatboost", "AutoLinearRegression", "AutoRidge",
    "AutoLasso", "AutoElasticNet", "AutoRandomForest",
)

#: ``hierarchicalforecast.methods.__all__``
RECONCILIATION_METHODS: tuple[str, ...] = (
    "BottomUp", "BottomUpSparse", "TopDown", "TopDownSparse", "MiddleOut",
    "MiddleOutSparse", "MinTrace", "MinTraceSparse", "OptimalCombination", "ERM",
)

# Family assignment for the neuralforecast estimators. Keys are the base model name; the
# Auto* variants inherit the family of their base.
_NF_FAMILY: dict[str, str] = {
    "RNN": "rnn", "GRU": "rnn", "LSTM": "rnn", "DilatedRNN": "rnn", "xLSTM": "rnn",
    "TCN": "cnn", "BiTCN": "cnn",
    "DeepAR": "deep_probabilistic", "DeepNPTS": "deep_probabilistic",
    "MLP": "mlp", "NBEATS": "mlp", "NBEATSx": "mlp", "NHITS": "mlp",
    "MLPMultivariate": "mlp", "TiDE": "mlp",
    "DLinear": "linear", "NLinear": "linear", "XLinear": "linear",
    "TFT": "transformer", "VanillaTransformer": "transformer", "Informer": "transformer",
    "Autoformer": "transformer", "FEDformer": "transformer", "PatchTST": "transformer",
    "iTransformer": "transformer", "TimesNet": "transformer", "TimeXer": "transformer",
    "TimeLLM": "transformer",
    "TSMixer": "mixer", "TSMixerx": "mixer", "SOFTS": "mixer", "SOFTSSharp": "mixer",
    "TimeMixer": "mixer",
    "KAN": "kan", "RMoK": "kan",
    "StemGNN": "graph", "HINT": "hierarchical",
}

_NF_MULTIVARIATE = frozenset(
    {"StemGNN", "MLPMultivariate", "TSMixer", "TSMixerx", "SOFTS", "SOFTSSharp",
     "TimeMixer", "RMoK", "iTransformer"}
)
_NF_EXOGENOUS = frozenset({"NBEATSx", "TFT", "TSMixerx", "TimeXer", "BiTCN", "TiDE"})
_NF_PROBABILISTIC = frozenset({"DeepAR", "DeepNPTS", "TFT", "HINT"})
#: FFT-based models that break under reduced precision.
_NF_FFT = frozenset({"TimesNet", "FEDformer", "Autoformer", "TimeMixer"})

_SF_FAMILY: dict[str, str] = {
    "ADIDA": "intermittent", "CrostonClassic": "intermittent",
    "CrostonOptimized": "intermittent", "CrostonSBA": "intermittent",
    "IMAPA": "intermittent", "TSB": "intermittent",
    "GARCH": "volatility", "ARCH": "volatility",
    "Naive": "baseline", "SeasonalNaive": "baseline", "HistoricAverage": "baseline",
    "RandomWalkWithDrift": "baseline", "WindowAverage": "baseline",
    "SeasonalWindowAverage": "baseline", "ConstantModel": "baseline",
    "ZeroModel": "baseline", "NaNModel": "baseline",
    "ConformalSeasonalPool": "conformal",
    "SklearnModel": "wrapper",
}

#: Baselines that MUST appear in every sweep as controls (constitution principle V).
MANDATORY_CONTROLS: tuple[str, ...] = ("uniform", "sf-seasonalnaive", "sf-naive", "sf-historicaverage")


def _sf_family(name: str) -> str:
    if name in _SF_FAMILY:
        return _SF_FAMILY[name]
    if "Theta" in name:
        return "theta"
    if "ExponentialSmoothing" in name or name in ("Holt", "HoltWinters", "AutoETS", "AutoCES"):
        return "exponential_smoothing"
    if "ARIMA" in name or name == "AutoRegressive":
        return "arima"
    if name in ("MSTL", "MFLES", "AutoMFLES", "TBATS", "AutoTBATS", "UCM"):
        return "decomposition"
    return "statistical"


# --------------------------------------------------------------------------------------
# TSFM registry -- Hugging Face repos, verified present on 2026-07-30
# --------------------------------------------------------------------------------------

TSFM_MODELS: tuple[dict[str, Any], ...] = (
    {"model_id": "chronos-2", "repo_id": "amazon/chronos-2", "class_name": "Chronos2Pipeline",
     "package": "chronos", "family": "tsfm", "priority": "p0",
     "notes": "highest-download TSFM; zero-shot, covariate-capable", "probabilistic": True},
    {"model_id": "chronos-bolt-tiny", "repo_id": "amazon/chronos-bolt-tiny",
     "class_name": "ChronosBoltPipeline", "package": "chronos", "family": "tsfm",
     "priority": "p0", "notes": "fastest Chronos variant; CPU-viable", "probabilistic": True},
    {"model_id": "chronos-t5-small", "repo_id": "amazon/chronos-t5-small",
     "class_name": "ChronosPipeline", "package": "chronos", "family": "tsfm",
     "notes": "T5 tokenised Chronos", "probabilistic": True},
    {"model_id": "chronos-t5-base", "repo_id": "amazon/chronos-t5-base",
     "class_name": "ChronosPipeline", "package": "chronos", "family": "tsfm",
     "probabilistic": True},
    {"model_id": "timesfm-2.5-transformers", "repo_id": "google/timesfm-2.5-200m-transformers",
     "class_name": "TimesFmModelForPrediction", "package": "transformers", "family": "tsfm",
     "priority": "p0",
     "notes": "transformers-native; preferred over the -pytorch checkpoint (no trust_remote_code)"},
    {"model_id": "granite-ttm-r2", "repo_id": "ibm-granite/granite-timeseries-ttm-r2",
     "class_name": "TinyTimeMixerForPrediction", "package": "transformers", "family": "tsfm",
     "priority": "p0", "license": "Apache-2.0",
     "notes": "Apache-licensed replacement for ibm-research/ttm-r3 (non-commercial)"},
    {"model_id": "granite-flowstate-r1", "repo_id": "ibm-granite/granite-timeseries-flowstate-r1",
     "class_name": "FlowStateForPrediction", "package": "transformers", "family": "tsfm",
     "notes": "9M params; smallest credible zero-shot forecaster"},
    {"model_id": "granite-patchtst", "repo_id": "ibm-granite/granite-timeseries-patchtst",
     "class_name": "PatchTSTForPrediction", "package": "transformers", "family": "tsfm"},
    {"model_id": "granite-patchtsmixer", "repo_id": "ibm-granite/granite-timeseries-patchtsmixer",
     "class_name": "PatchTSMixerForPrediction", "package": "transformers", "family": "tsfm"},
    {"model_id": "moirai-2.0-small", "repo_id": "Salesforce/moirai-2.0-R-small",
     "class_name": "MoiraiForecast", "package": "uni2ts", "family": "tsfm", "priority": "p0",
     "probabilistic": True},
    {"model_id": "moirai-1.0-base", "repo_id": "Salesforce/moirai-1.0-R-base",
     "class_name": "MoiraiForecast", "package": "uni2ts", "family": "tsfm",
     "probabilistic": True},
    {"model_id": "tirex-2", "repo_id": "NX-AI/TiRex-2", "class_name": "TiRex",
     "package": "tirex", "family": "tsfm", "notes": "xLSTM-based; successor to TiRex"},
    {"model_id": "toto-open-base", "repo_id": "Datadog/Toto-Open-Base-1.0",
     "class_name": "TotoForecaster", "package": "toto", "family": "tsfm",
     "probabilistic": True, "notes": "observability-domain pretraining"},
    {"model_id": "toto-2.0-4m", "repo_id": "Datadog/Toto-2.0-4m",
     "class_name": "TotoForecaster", "package": "toto", "family": "tsfm",
     "probabilistic": True},
    {"model_id": "moment-1-small", "repo_id": "AutonLab/MOMENT-1-small",
     "class_name": "MOMENTPipeline", "package": "momentfm", "family": "tsfm",
     "notes": "general TS embedding model; forecasting head required"},
    {"model_id": "moment-1-large", "repo_id": "AutonLab/MOMENT-1-large",
     "class_name": "MOMENTPipeline", "package": "momentfm", "family": "tsfm"},
    {"model_id": "lag-llama", "repo_id": "time-series-foundation-models/Lag-Llama",
     "class_name": "LagLlamaEstimator", "package": "lag_llama", "family": "tsfm",
     "probabilistic": True},
    {"model_id": "kronos-base", "repo_id": "NeoQuasar/Kronos-base",
     "class_name": "KronosPredictor", "package": "kronos", "family": "tsfm",
     "notes": "discrete-token financial series model"},
    {"model_id": "sundial-base", "repo_id": "thuml/sundial-base-128m",
     "class_name": "SundialForPrediction", "package": "transformers", "family": "tsfm",
     "probabilistic": True},
    {"model_id": "tabpfn-ts", "repo_id": "Prior-Labs/TabPFN-v2-clf",
     "class_name": "TabPFNTimeSeries", "package": "tabpfn_time_series",
     "family": "foundation_tabular", "task": "candidate",
     "notes": "tabular foundation model applied to the candidate matrix"},
    {"model_id": "t0-alpha", "repo_id": "theforecastingcompany/t0-alpha",
     "class_name": "T0Pipeline", "package": "tfc", "family": "tsfm", "priority": "p2",
     "notes": "GATED: weights resolve to zero bytes without accepted terms; kept as a "
              "known-blocked entry so the availability probe reports it explicitly"},
)


# --------------------------------------------------------------------------------------
# Registry construction
# --------------------------------------------------------------------------------------

def _builtin_and_sklearn() -> list[ModelEntry]:
    """Always-available controls and the sklearn tier."""
    return [
        ModelEntry("uniform", "theory", "builtin", "candidate", "UniformCandidateAdapter",
                   priority="p0", capabilities=("probability", "ranking", "control"),
                   notes="exact theoretical uniform; mandatory control",
                   supports_probabilistic=True),
        ModelEntry("frequency", "frequency", "builtin", "candidate", "FrequencyCandidateAdapter",
                   priority="p0", capabilities=("probability", "ranking"),
                   supports_probabilistic=True),
        ModelEntry("position-median", "theory", "builtin", "position", "TheoryMedianAdapter",
                   priority="p0", capabilities=("position", "control"),
                   notes="exact MAE-floor predictor; mandatory control"),
        ModelEntry("position-modal", "theory", "builtin", "position", "TheoryModalAdapter",
                   priority="p0", capabilities=("position", "control"),
                   notes="exact within-tau ceiling predictor; mandatory control"),
        ModelEntry("logistic", "linear", "sklearn", "candidate", "LogisticRegression",
                   priority="p0", package="sklearn",
                   capabilities=("probability", "exogenous"),
                   default_params={"C": 1.0, "max_iter": 1000}, supports_exogenous=True,
                   supports_probabilistic=True),
        ModelEntry("ridge", "linear", "sklearn", "position", "Ridge", priority="p0",
                   package="sklearn", capabilities=("position", "exogenous"),
                   default_params={"alpha": 1.0}, supports_exogenous=True),
        ModelEntry("elastic-net", "linear", "sklearn", "position", "ElasticNet",
                   package="sklearn", capabilities=("position", "exogenous"),
                   default_params={"alpha": 0.01, "l1_ratio": 0.5, "max_iter": 5000},
                   supports_exogenous=True),
        ModelEntry("random-forest", "tree", "sklearn", "candidate", "RandomForestClassifier",
                   priority="p0", package="sklearn", capabilities=("probability", "exogenous"),
                   default_params={"n_estimators": 300, "min_samples_leaf": 3, "n_jobs": -1},
                   supports_exogenous=True, supports_probabilistic=True),
        ModelEntry("extra-trees", "tree", "sklearn", "candidate", "ExtraTreesClassifier",
                   priority="p0", package="sklearn", capabilities=("probability", "exogenous"),
                   default_params={"n_estimators": 300, "min_samples_leaf": 2, "n_jobs": -1},
                   supports_exogenous=True, supports_probabilistic=True),
        ModelEntry("hist-gradient-boosting", "tree", "sklearn", "candidate",
                   "HistGradientBoostingClassifier", priority="p0", package="sklearn",
                   capabilities=("probability", "exogenous"),
                   default_params={"learning_rate": 0.05, "max_iter": 200},
                   supports_exogenous=True, supports_probabilistic=True),
        ModelEntry("isotonic-calibrated-logistic", "calibrated", "sklearn", "candidate",
                   "CalibratedClassifierCV", package="sklearn",
                   capabilities=("probability", "calibration"),
                   default_params={"method": "isotonic", "cv": 3},
                   supports_probabilistic=True,
                   notes="wraps logistic; makes the calibration layer measurable"),
        ModelEntry("lightgbm-classifier", "tree", "lightgbm", "candidate", "LGBMClassifier",
                   priority="p0", package="lightgbm", capabilities=("probability", "exogenous"),
                   default_params={"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 31},
                   supports_exogenous=True, supports_probabilistic=True),
        ModelEntry("lightgbm-position", "tree", "lightgbm", "position", "LGBMRegressor",
                   package="lightgbm", capabilities=("position", "exogenous"),
                   default_params={"n_estimators": 400, "learning_rate": 0.03},
                   supports_exogenous=True),
        ModelEntry("xgboost-classifier", "tree", "xgboost", "candidate", "XGBClassifier",
                   package="xgboost", capabilities=("probability", "exogenous"),
                   default_params={"n_estimators": 400, "learning_rate": 0.03, "max_depth": 5},
                   supports_exogenous=True, supports_probabilistic=True),
        ModelEntry("catboost-classifier", "tree", "catboost", "candidate", "CatBoostClassifier",
                   package="catboost", capabilities=("probability", "exogenous"),
                   default_params={"iterations": 400, "learning_rate": 0.03, "verbose": False},
                   supports_exogenous=True, supports_probabilistic=True),
    ]


def _framework_tier() -> list[ModelEntry]:
    return [
        ModelEntry("autogluon-timeseries", "automl", "autogluon", "position_series",
                   "TimeSeriesPredictor", package="autogluon",
                   capabilities=("position", "probability", "automl"),
                   supports_probabilistic=True),
        ModelEntry("darts-ensemble", "framework", "darts", "position_series",
                   "RegressionEnsembleModel", package="darts",
                   capabilities=("position", "ensemble")),
        ModelEntry("gluonts-deepar", "deep_probabilistic", "gluonts", "position_series",
                   "DeepAREstimator", package="gluonts",
                   capabilities=("position", "probability"), supports_probabilistic=True),
        ModelEntry("reservoir-esn", "reservoir", "reservoirpy", "position", "ESN",
                   package="reservoirpy", capabilities=("position",)),
        ModelEntry("sktime-ensemble", "framework", "sktime", "position_series",
                   "EnsembleForecaster", package="sktime",
                   capabilities=("position", "ensemble")),
        ModelEntry("skforecast-recursive", "lag_ml", "skforecast", "position_series",
                   "ForecasterRecursive", package="skforecast",
                   capabilities=("position", "exogenous"), supports_exogenous=True),
    ]


def build_catalog() -> list[ModelEntry]:
    """Assemble the full registry. Order is stable: controls first, then by library."""
    entries: list[ModelEntry] = list(_builtin_and_sklearn())

    for name in STATSFORECAST_MODELS:
        family = _sf_family(name)
        entries.append(
            ModelEntry(
                model_id=f"sf-{name.lower()}",
                family=family,
                library="statsforecast",
                task="position_series",
                class_name=name,
                priority="p0" if family in ("baseline", "conformal") else "p1",
                package="statsforecast",
                capabilities=("position",) + (("probability",) if family == "conformal" else ()),
                supports_probabilistic=family == "conformal",
                notes="mandatory control" if name in ("SeasonalNaive", "Naive", "HistoricAverage")
                else "",
            )
        )

    for name in NEURALFORECAST_MODELS:
        entries.append(
            ModelEntry(
                model_id=f"nf-{name.lower()}",
                family=_NF_FAMILY.get(name, "deep"),
                library="neuralforecast",
                task="position_series",
                class_name=name,
                package="neuralforecast",
                capabilities=("position",)
                + (("exogenous",) if name in _NF_EXOGENOUS else ())
                + (("probability",) if name in _NF_PROBABILISTIC else ())
                + (("multivariate",) if name in _NF_MULTIVARIATE else ()),
                supports_exogenous=name in _NF_EXOGENOUS,
                supports_probabilistic=name in _NF_PROBABILISTIC,
                multivariate=name in _NF_MULTIVARIATE,
                requires_n_series=name in _NF_MULTIVARIATE,
                notes="FFT kernel: forces 32-true precision" if name in _NF_FFT else "",
            )
        )

    for name in NEURALFORECAST_AUTOMODELS:
        base = name[4:]
        entries.append(
            ModelEntry(
                model_id=f"nfauto-{base.lower()}",
                family=_NF_FAMILY.get(base, "deep"),
                library="neuralforecast_auto",
                task="position_series",
                class_name=name,
                package="neuralforecast",
                capabilities=("position", "hpo")
                + (("multivariate",) if base in _NF_MULTIVARIATE else ()),
                multivariate=base in _NF_MULTIVARIATE,
                requires_n_series=base in _NF_MULTIVARIATE,
                notes="official AutoModel; backend/search resolved at runtime"
                + ("; FFT kernel forces 32-true precision" if base in _NF_FFT else ""),
            )
        )

    for name in MLFORECAST_AUTOMODELS:
        entries.append(
            ModelEntry(
                model_id=f"mfauto-{name[4:].lower()}",
                family="lag_ml",
                library="mlforecast_auto",
                task="position_series",
                class_name=name,
                package="mlforecast",
                capabilities=("position", "exogenous", "hpo"),
                supports_exogenous=True,
                notes="AutoMLForecast wrapper with upstream default search space",
            )
        )

    for name in RECONCILIATION_METHODS:
        entries.append(
            ModelEntry(
                model_id=f"hf-{name.lower()}",
                family="reconciliation",
                library="hierarchicalforecast",
                task="reconciliation",
                class_name=name,
                package="hierarchicalforecast",
                capabilities=("reconciliation", "coherence"),
                notes="enforces coherence across the number/decade/parity hierarchy",
            )
        )

    for spec in TSFM_MODELS:
        entries.append(
            ModelEntry(
                model_id=str(spec["model_id"]),
                family=str(spec.get("family", "tsfm")),
                library=str(spec.get("library", "tsfm")),
                task=str(spec.get("task", "foundation")),  # type: ignore[arg-type]
                class_name=str(spec["class_name"]),
                priority=str(spec.get("priority", "p1")),
                package=str(spec["package"]),
                capabilities=("zero_shot", "position")
                + (("probability",) if spec.get("probabilistic") else ()),
                default_params={"repo_id": spec["repo_id"]},
                repo_id=str(spec["repo_id"]),
                revision=spec.get("revision"),
                license=spec.get("license"),
                supports_probabilistic=bool(spec.get("probabilistic")),
                notes=str(spec.get("notes", "")),
            )
        )

    entries.extend(_framework_tier())

    seen: set[str] = set()
    for entry in entries:
        if entry.model_id in seen:
            raise AssertionError(f"duplicate model_id in catalog: {entry.model_id}")
        seen.add(entry.model_id)
    return entries


def catalog_counts() -> dict[str, int]:
    """Counts computed from the catalog. Never hand-typed (constitution principle I)."""
    entries = build_catalog()
    by_lib: dict[str, int] = {}
    for e in entries:
        by_lib[e.library] = by_lib.get(e.library, 0) + 1
    by_lib["TOTAL"] = len(entries)
    by_lib["_unpinned_tsfm"] = sum(1 for e in entries if e.revision_status == "UNPINNED")
    by_lib["_mandatory_controls"] = len(MANDATORY_CONTROLS)
    return dict(sorted(by_lib.items()))


def catalog_by_library() -> dict[str, list[ModelEntry]]:
    out: dict[str, list[ModelEntry]] = {}
    for e in build_catalog():
        out.setdefault(e.library, []).append(e)
    return out
