from __future__ import annotations

# ruff: noqa: E501,I001,UP035

from dataclasses import asdict, dataclass, field
from importlib.util import find_spec
from typing import Any, Iterable


PACKAGE_MODULE_ALIASES = {
    "chronos": ("chronos",),
}


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    family: str
    library: str
    task: str
    class_name: str
    priority: str = "p1"
    package: str | None = None
    capabilities: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def available(self) -> bool:
        if self.package is None:
            return True
        packages = PACKAGE_MODULE_ALIASES.get(self.package, (self.package,))
        return any(find_spec(package) is not None for package in packages)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"available": self.available}


# The catalog is deliberately declarative: adding a model does not require changing
# orchestration code. Unsupported/absent optional packages are reported, not hidden.
MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec("uniform", "theory", "builtin", "candidate", "UniformCandidateAdapter", "p0", capabilities=("probability", "ranking")),
    ModelSpec("frequency", "frequency", "builtin", "candidate", "FrequencyCandidateAdapter", "p0", capabilities=("probability", "ranking")),
    ModelSpec("logistic", "linear", "sklearn", "candidate", "LogisticRegression", "p0", "sklearn", ("probability", "exogenous"), {"C": 1.0, "max_iter": 1000}),
    ModelSpec("ridge-position", "linear", "sklearn", "position_series", "Ridge", "p0", "sklearn", ("position", "exogenous"), {"alpha": 1.0}),
    ModelSpec("elasticnet-position", "linear", "sklearn", "position_series", "ElasticNet", "p1", "sklearn", ("position", "exogenous"), {"alpha": 0.01, "l1_ratio": 0.5, "max_iter": 5000}),
    ModelSpec("random-forest", "tree", "sklearn", "candidate", "RandomForestClassifier", "p1", "sklearn", ("probability", "exogenous"), {"n_estimators": 300, "min_samples_leaf": 3, "n_jobs": -1}),
    ModelSpec("extra-trees", "tree", "sklearn", "candidate", "ExtraTreesClassifier", "p0", "sklearn", ("probability", "exogenous"), {"n_estimators": 300, "min_samples_leaf": 2, "n_jobs": -1}),
    ModelSpec("hist-gradient-boosting", "tree", "sklearn", "candidate", "HistGradientBoostingClassifier", "p0", "sklearn", ("probability", "exogenous"), {"max_iter": 200, "learning_rate": 0.05}),
    ModelSpec("lightgbm-classifier", "tree", "lightgbm", "candidate", "LGBMClassifier", "p0", "lightgbm", ("probability", "ranking", "exogenous", "gpu_optional"), {"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 31}),
    ModelSpec("lightgbm-position", "tree", "lightgbm", "position_series", "LGBMRegressor", "p0", "lightgbm", ("position", "exogenous", "gpu_optional"), {"n_estimators": 400, "learning_rate": 0.03}),
    ModelSpec("xgboost-classifier", "tree", "xgboost", "candidate", "XGBClassifier", "p1", "xgboost", ("probability", "exogenous", "gpu_optional"), {"n_estimators": 400, "learning_rate": 0.03, "max_depth": 5}),
    ModelSpec("catboost-classifier", "tree", "catboost", "candidate", "CatBoostClassifier", "p1", "catboost", ("probability", "exogenous", "gpu_optional"), {"iterations": 400, "learning_rate": 0.03, "verbose": False}),
    ModelSpec("stats-naive", "statistical", "statsforecast", "position_series", "Naive", "p0", "statsforecast"),
    ModelSpec("stats-historic-average", "statistical", "statsforecast", "position_series", "HistoricAverage", "p0", "statsforecast"),
    ModelSpec("stats-autoarima", "statistical", "statsforecast", "position_series", "AutoARIMA", "p0", "statsforecast"),
    ModelSpec("stats-autoets", "statistical", "statsforecast", "position_series", "AutoETS", "p0", "statsforecast"),
    ModelSpec("stats-autotheta", "statistical", "statsforecast", "position_series", "AutoTheta", "p0", "statsforecast"),
    ModelSpec("stats-autoces", "statistical", "statsforecast", "position_series", "AutoCES", "p1", "statsforecast"),
    ModelSpec("stats-croston", "intermittent", "statsforecast", "candidate_series", "CrostonClassic", "p1", "statsforecast"),
    ModelSpec("stats-tsb", "intermittent", "statsforecast", "candidate_series", "TSB", "p1", "statsforecast"),
    ModelSpec("mlforecast-ridge", "lag_ml", "mlforecast", "position_series", "Ridge", "p0", "mlforecast", ("lags", "exogenous")),
    ModelSpec("mlforecast-lightgbm", "lag_ml", "mlforecast", "position_series", "LGBMRegressor", "p0", "mlforecast", ("lags", "exogenous", "gpu_optional")),
    ModelSpec("nf-dlinear", "deep", "neuralforecast", "position_series", "DLinear", "p0", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-nlinear", "deep", "neuralforecast", "position_series", "NLinear", "p0", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-nhits", "deep", "neuralforecast", "position_series", "NHITS", "p0", "neuralforecast", ("gpu", "checkpoint", "exogenous")),
    ModelSpec("nf-nbeats", "deep", "neuralforecast", "position_series", "NBEATS", "p1", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-nbeatsx", "deep", "neuralforecast", "position_series", "NBEATSx", "p1", "neuralforecast", ("gpu", "checkpoint", "exogenous")),
    ModelSpec("nf-tide", "deep", "neuralforecast", "position_series", "TiDE", "p0", "neuralforecast", ("gpu", "checkpoint", "exogenous")),
    ModelSpec("nf-tcn", "deep", "neuralforecast", "position_series", "TCN", "p0", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-gru", "deep", "neuralforecast", "position_series", "GRU", "p0", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-lstm", "deep", "neuralforecast", "position_series", "LSTM", "p1", "neuralforecast", ("gpu", "checkpoint")),
    ModelSpec("nf-deepar", "deep_probabilistic", "neuralforecast", "position_series", "DeepAR", "p1", "neuralforecast", ("gpu", "probabilistic")),
    ModelSpec("nf-tft", "transformer", "neuralforecast", "position_series", "TFT", "p1", "neuralforecast", ("gpu", "exogenous", "attention")),
    ModelSpec("nf-patchtst", "transformer", "neuralforecast", "position_series", "PatchTST", "p1", "neuralforecast", ("gpu",)),
    ModelSpec("nf-timesnet", "transformer", "neuralforecast", "position_series", "TimesNet", "p1", "neuralforecast", ("gpu",)),
    ModelSpec("nf-tsmixer", "mixer", "neuralforecast", "position_series", "TSMixer", "p1", "neuralforecast", ("gpu", "multiseries")),
    ModelSpec("nf-timemixer", "mixer", "neuralforecast", "position_series", "TimeMixer", "p2", "neuralforecast", ("gpu",)),
    ModelSpec("nf-itransformer", "transformer", "neuralforecast", "position_series", "iTransformer", "p2", "neuralforecast", ("gpu", "multivariate")),
    ModelSpec("nf-vanilla-transformer", "transformer", "neuralforecast", "position_series", "VanillaTransformer", "p2", "neuralforecast", ("gpu",)),
    ModelSpec("nf-auto-rnn", "rnn", "neuralforecast_auto", "position_series", "AutoRNN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-lstm", "rnn", "neuralforecast_auto", "position_series", "AutoLSTM", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-gru", "rnn", "neuralforecast_auto", "position_series", "AutoGRU", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-tcn", "cnn", "neuralforecast_auto", "position_series", "AutoTCN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-deepar", "deep_probabilistic", "neuralforecast_auto", "position_series", "AutoDeepAR", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-dilatedrnn", "rnn", "neuralforecast_auto", "position_series", "AutoDilatedRNN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-bitcn", "cnn", "neuralforecast_auto", "position_series", "AutoBiTCN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-mlp", "mlp", "neuralforecast_auto", "position_series", "AutoMLP", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-nbeats", "mlp", "neuralforecast_auto", "position_series", "AutoNBEATS", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-nbeatsx", "mlp", "neuralforecast_auto", "position_series", "AutoNBEATSx", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-nhits", "mlp", "neuralforecast_auto", "position_series", "AutoNHITS", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-dlinear", "linear", "neuralforecast_auto", "position_series", "AutoDLinear", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-nlinear", "linear", "neuralforecast_auto", "position_series", "AutoNLinear", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-tide", "mlp", "neuralforecast_auto", "position_series", "AutoTiDE", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-deepnpts", "deep_probabilistic", "neuralforecast_auto", "position_series", "AutoDeepNPTS", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-kan", "kan", "neuralforecast_auto", "position_series", "AutoKAN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-tft", "transformer", "neuralforecast_auto", "position_series", "AutoTFT", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-vanilla-transformer", "transformer", "neuralforecast_auto", "position_series", "AutoVanillaTransformer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-informer", "transformer", "neuralforecast_auto", "position_series", "AutoInformer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-autoformer", "transformer", "neuralforecast_auto", "position_series", "AutoAutoformer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-fedformer", "transformer", "neuralforecast_auto", "position_series", "AutoFEDformer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-patchtst", "transformer", "neuralforecast_auto", "position_series", "AutoPatchTST", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-itransformer", "transformer", "neuralforecast_auto", "position_series", "AutoiTransformer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-timexer", "transformer", "neuralforecast_auto", "position_series", "AutoTimeXer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-timesnet", "transformer", "neuralforecast_auto", "position_series", "AutoTimesNet", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-stemgnn", "graph", "neuralforecast_auto", "position_series", "AutoStemGNN", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-hint", "hierarchical", "neuralforecast_auto", "position_series", "AutoHINT", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-tsmixer", "mixer", "neuralforecast_auto", "position_series", "AutoTSMixer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-tsmixerx", "mixer", "neuralforecast_auto", "position_series", "AutoTSMixerx", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-mlp-multivariate", "mlp", "neuralforecast_auto", "position_series", "AutoMLPMultivariate", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-softs", "mixer", "neuralforecast_auto", "position_series", "AutoSOFTS", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-timemixer", "mixer", "neuralforecast_auto", "position_series", "AutoTimeMixer", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("nf-auto-rmok", "kan", "neuralforecast_auto", "position_series", "AutoRMoK", "p1", "neuralforecast", ("gpu", "auto_hpo", "optuna", "ray", "checkpoint"), notes="Official NeuralForecast AutoModel; backend/search resolved at runtime"),
    ModelSpec("autogluon-timeseries", "automl", "autogluon", "position_series", "TimeSeriesPredictor", "p1", "autogluon", ("ensemble", "probabilistic", "zero_shot")),
    ModelSpec("darts-ensemble", "framework", "darts", "position_series", "RegressionEnsembleModel", "p2", "darts", ("ensemble", "probabilistic")),
    ModelSpec(
        "gluonts-deepar",
        "deep_probabilistic",
        "gluonts",
        "position_series",
        "DeepAREstimator",
        "p2",
        "gluonts",
        ("probabilistic",),
        {"epochs": 1, "num_batches_per_epoch": 2, "context_length": 16, "num_samples": 20},
    ),
    ModelSpec(
        "reservoir-esn",
        "reservoir",
        "reservoirpy",
        "position",
        "ESN",
        "p1",
        "reservoirpy",
        ("position",),
        {"reservoir_size": 50, "spectral_radius": 0.9, "leak_rate": 0.3, "ridge_alpha": 1e-6},
    ),
    ModelSpec(
        "chronos-bolt-tiny",
        "tsfm",
        "chronos",
        "foundation",
        "ChronosBoltPipeline",
        "p1",
        "chronos",
        ("zero_shot", "probabilistic", "gpu_optional"),
        {
            "model_name": "amazon/chronos-bolt-tiny",
            "revision": "a0e552de83495b5c28c14c71c374f3e33280b340",
        },
    ),
    ModelSpec("chronos-2-small", "tsfm", "chronos", "foundation", "Chronos2Pipeline", "p1", "chronos", ("zero_shot", "fine_tuning", "exogenous"), {"model_name": "autogluon/chronos-2-small"}),
    ModelSpec("timesfm-2.5", "tsfm", "timesfm", "foundation", "TimesFM", "p1", "timesfm", ("zero_shot", "fine_tuning", "exogenous", "gpu")),
    ModelSpec("granite-ttm", "tsfm", "transformers", "foundation", "TinyTimeMixerForPrediction", "p1", "transformers", ("zero_shot", "fine_tuning", "gpu_optional")),
    ModelSpec(
        "tirex",
        "tsfm",
        "tirex",
        "foundation",
        "TiRex",
        "p1",
        "tirex",
        ("zero_shot", "probabilistic", "gpu_optional"),
        {
            "model_name": "NX-AI/TiRex-2",
            "revision": "05e5b26db52bfb256f1ae1bdf785589850482de3",
        },
    ),
    ModelSpec(
        "moirai",
        "tsfm",
        "uni2ts",
        "foundation",
        "Moirai2Forecast",
        "p2",
        "uni2ts",
        ("zero_shot", "probabilistic", "gpu"),
        {
            "model_name": "Salesforce/moirai-2.0-R-small",
            "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
        },
    ),
    ModelSpec(
        "sundial",
        "tsfm",
        "transformers",
        "foundation",
        "SundialForPrediction",
        "p2",
        "transformers",
        ("zero_shot", "generative", "gpu"),
        {
            "model_name": "thuml/sundial-base-128m",
            "revision": "3212e42564493f520593e5414af4367fc4b49226",
            "trust_remote_code": True,
        },
    ),
    ModelSpec("tabpfn-ts", "foundation_tabular", "tabpfn_time_series", "candidate", "TabPFNTimeSeries", "p1", "tabpfn_time_series", ("zero_shot", "probability", "gpu_optional")),
)


def get_model_spec(model_id: str) -> ModelSpec:
    for spec in MODEL_SPECS:
        if spec.model_id == model_id:
            return spec
    raise KeyError(f"unknown model_id: {model_id}")


def list_model_specs(*, priority: str | None = None, available_only: bool = False) -> list[ModelSpec]:
    values: Iterable[ModelSpec] = MODEL_SPECS
    if priority:
        values = (item for item in values if item.priority == priority)
    if available_only:
        values = (item for item in values if item.available)
    return list(values)
