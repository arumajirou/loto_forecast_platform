"""Pinned skforecast 0.23.0 implementation manifest for Expanded v2 Phase 4A.

The manifest is intentionally finite. skforecast wrapper classes can accept many
arbitrary scikit-learn compatible estimators; Expanded v2 therefore records the
major public forecasting strategies plus scientifically meaningful estimator
families and explicitly listed foundation/statistical implementations instead of
creating an unbounded wrapper x estimator Cartesian product.
"""

from __future__ import annotations

from dataclasses import dataclass

SKFORECAST_VERSION = "0.23.0"
SKFORECAST_SOURCE_TAG = "v0.23.0"
SKFORECAST_SOURCE_REVISION = "c881d5d350426985c1c31373077b7d5b620f233d"
SKFORECAST_OPERATOR_EVIDENCE_REVISION = "9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd"

OPERATOR_LOCAL_EVIDENCE = "OPERATOR_LOCAL_EVIDENCE"
SOURCE_DECLARED = "SOURCE_DECLARED"
OPERATOR_LOCAL_PASS = "OPERATOR_LOCAL_PASS"
NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class SkforecastImplementationSpec:
    """One reviewed skforecast implementation identity before catalog wrapping."""

    implementation_id: str
    algorithm_id: str
    class_name: str
    family: str
    source_alias: str
    capabilities: tuple[str, ...]
    runtime_status: str = NOT_RUN
    evidence_class: str = SOURCE_DECLARED
    evidence_revision: str | None = None
    routability: str = "NOT_CURRENT_MAIN_ROUTABLE"
    block_reason: str | None = None
    source_declared: bool = True
    notes: str = ""


_COMMON_REGRESSION = ("position_series", "exogenous")
_FOUNDATION_EXOG = (
    "position_series",
    "foundation",
    "exogenous",
    "probabilistic",
)
_FOUNDATION_NO_EXOG = (
    "position_series",
    "foundation",
    "probabilistic",
)


def _operator_pass(
    implementation_id: str,
    *,
    algorithm_id: str,
    class_name: str,
    family: str,
    source_alias: str,
    capabilities: tuple[str, ...],
    source_declared: bool = False,
    notes: str = "",
) -> SkforecastImplementationSpec:
    return SkforecastImplementationSpec(
        implementation_id=implementation_id,
        algorithm_id=algorithm_id,
        class_name=class_name,
        family=family,
        source_alias=source_alias,
        capabilities=capabilities,
        runtime_status=OPERATOR_LOCAL_PASS,
        evidence_class=OPERATOR_LOCAL_EVIDENCE,
        evidence_revision=SKFORECAST_OPERATOR_EVIDENCE_REVISION,
        source_declared=source_declared,
        notes=notes,
    )


SKFORECAST_IMPLEMENTATION_SPECS: tuple[SkforecastImplementationSpec, ...] = (
    # ForecasterRecursive: representative scientifically distinct estimator families.
    _operator_pass(
        "skforecast-recursive-ridge",
        algorithm_id="recursive-ridge",
        class_name="ForecasterRecursive",
        family="recursive_regression",
        source_alias="sklearn.linear_model.Ridge",
        capabilities=_COMMON_REGRESSION,
    ),
    _operator_pass(
        "skforecast-recursive-histgb",
        algorithm_id="recursive-hist-gradient-boosting",
        class_name="ForecasterRecursive",
        family="recursive_tree_boosting",
        source_alias="sklearn.ensemble.HistGradientBoostingRegressor",
        capabilities=_COMMON_REGRESSION,
    ),
    _operator_pass(
        "skforecast-recursive-lightgbm",
        algorithm_id="recursive-lightgbm",
        class_name="ForecasterRecursive",
        family="recursive_external_boosting",
        source_alias="lightgbm.LGBMRegressor",
        capabilities=_COMMON_REGRESSION,
    ),
    _operator_pass(
        "skforecast-recursive-xgboost",
        algorithm_id="recursive-xgboost",
        class_name="ForecasterRecursive",
        family="recursive_external_boosting",
        source_alias="xgboost.XGBRegressor",
        capabilities=_COMMON_REGRESSION,
    ),
    _operator_pass(
        "skforecast-recursive-catboost",
        algorithm_id="recursive-catboost",
        class_name="ForecasterRecursive",
        family="recursive_external_boosting",
        source_alias="catboost.CatBoostRegressor",
        capabilities=_COMMON_REGRESSION,
    ),
    # Public recursive classifier strategy. The exact LogisticRegression binding is
    # project-reviewed rather than an upstream-prescribed canonical estimator.
    SkforecastImplementationSpec(
        implementation_id="skforecast-recursive-classifier-logistic",
        algorithm_id="recursive-classifier-logistic",
        class_name="ForecasterRecursiveClassifier",
        family="recursive_classifier",
        source_alias="sklearn.linear_model.LogisticRegression",
        capabilities=("position_series", "exogenous", "classification"),
        source_declared=False,
        notes=(
            "source-declared ForecasterRecursiveClassifier strategy with a reviewed "
            "representative sklearn classifier binding; construction/prediction NOT_RUN"
        ),
    ),
    _operator_pass(
        "skforecast-direct-ridge",
        algorithm_id="direct-ridge",
        class_name="ForecasterDirect",
        family="direct_regression",
        source_alias="sklearn.linear_model.Ridge",
        capabilities=_COMMON_REGRESSION,
    ),
    _operator_pass(
        "skforecast-recursive-multiseries-ridge",
        algorithm_id="recursive-multiseries-ridge",
        class_name="ForecasterRecursiveMultiSeries",
        family="multi_series",
        source_alias="sklearn.linear_model.Ridge",
        capabilities=("multi_series", "exogenous"),
    ),
    _operator_pass(
        "skforecast-direct-multivariate-ridge",
        algorithm_id="direct-multivariate-ridge",
        class_name="ForecasterDirectMultiVariate",
        family="multivariate_direct",
        source_alias="sklearn.linear_model.Ridge",
        capabilities=("multivariate", "exogenous"),
    ),
    _operator_pass(
        "skforecast-equivalent-date",
        algorithm_id="equivalent-date",
        class_name="ForecasterEquivalentDate",
        family="baseline",
        source_alias="ForecasterEquivalentDate",
        capabilities=("position_series", "baseline"),
        source_declared=True,
    ),
    # ForecasterStats explicitly lists seven supported statistical implementations.
    _operator_pass(
        "skforecast-stats-arar",
        algorithm_id="arar",
        class_name="ForecasterStats",
        family="statistical_wrapper",
        source_alias="skforecast.stats.Arar",
        capabilities=("position_series", "statistical"),
        source_declared=True,
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-arima",
        algorithm_id="arima",
        class_name="ForecasterStats",
        family="statistical_wrapper",
        source_alias="skforecast.stats.Arima",
        capabilities=("position_series", "statistical"),
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-ets",
        algorithm_id="ets",
        class_name="ForecasterStats",
        family="statistical_wrapper",
        source_alias="skforecast.stats.Ets",
        capabilities=("position_series", "statistical"),
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-sarimax",
        algorithm_id="sarimax",
        class_name="ForecasterStats",
        family="statistical_wrapper",
        source_alias="skforecast.stats.Sarimax",
        capabilities=("position_series", "statistical", "exogenous"),
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-sktime-arima",
        algorithm_id="arima",
        class_name="ForecasterStats",
        family="statistical_wrapper_external",
        source_alias="sktime.forecasting.ARIMA",
        capabilities=("position_series", "statistical", "optional_dependency"),
        notes="supported by ForecasterStats; underlying sktime dependency pin is a separate gate",
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-aeon-arima",
        algorithm_id="arima",
        class_name="ForecasterStats",
        family="statistical_wrapper_external",
        source_alias="aeon.forecasting.stats.ARIMA",
        capabilities=("position_series", "statistical", "optional_dependency"),
        notes="supported by ForecasterStats; underlying aeon dependency pin is a separate gate",
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-stats-aeon-ets",
        algorithm_id="ets",
        class_name="ForecasterStats",
        family="statistical_wrapper_external",
        source_alias="aeon.forecasting.stats.ETS",
        capabilities=("position_series", "statistical", "optional_dependency"),
        notes="supported by ForecasterStats; underlying aeon dependency pin is a separate gate",
    ),
    # Deep-learning strategy variants exercised in the operator lane.
    _operator_pass(
        "skforecast-rnn-lstm",
        algorithm_id="lstm",
        class_name="ForecasterRnn",
        family="rnn",
        source_alias="LSTM",
        capabilities=("position_series", "gpu", "cpu_fallback"),
    ),
    _operator_pass(
        "skforecast-rnn-gru",
        algorithm_id="gru",
        class_name="ForecasterRnn",
        family="rnn",
        source_alias="GRU",
        capabilities=("position_series", "gpu"),
    ),
    # FoundationModel 0.23.0 explicitly lists all model IDs below. Chronos-2 has
    # three distinct selectable model IDs sharing one scientific algorithm_id.
    SkforecastImplementationSpec(
        implementation_id="skforecast-foundation-chronos2-amazon",
        algorithm_id="chronos-2",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="amazon/chronos-2",
        capabilities=_FOUNDATION_EXOG,
    ),
    _operator_pass(
        "skforecast-foundation-chronos2-small",
        algorithm_id="chronos-2",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="autogluon/chronos-2-small",
        capabilities=_FOUNDATION_EXOG + ("gpu", "cpu_fallback"),
        source_declared=True,
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-foundation-chronos2-synth",
        algorithm_id="chronos-2",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="autogluon/chronos-2-synth",
        capabilities=_FOUNDATION_EXOG,
    ),
    _operator_pass(
        "skforecast-foundation-timesfm25",
        algorithm_id="timesfm-2.5",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="google/timesfm-2.5-200m-pytorch",
        capabilities=_FOUNDATION_NO_EXOG + ("gpu", "cpu_fallback"),
        source_declared=True,
        notes="skforecast TimesFM adapter explicitly does not support exogenous variables",
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-foundation-moirai2",
        algorithm_id="moirai-2",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="Salesforce/moirai-2.0-R-small",
        capabilities=_FOUNDATION_NO_EXOG + ("gpu", "cpu_fallback"),
        runtime_status="BLOCKED_DEPENDENCY_CONFLICT",
        evidence_class=OPERATOR_LOCAL_EVIDENCE,
        evidence_revision=SKFORECAST_OPERATOR_EVIDENCE_REVISION,
        routability="BLOCKED",
        block_reason="UPSTREAM_DEPENDENCY_CONFLICT",
        notes=(
            "runtime passed only under a controlled unsupported metadata override; "
            "normal dependency routability remains blocked"
        ),
    ),
    _operator_pass(
        "skforecast-foundation-tabicl-v2",
        algorithm_id="tabicl-v2",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="soda-inria/tabicl",
        capabilities=_FOUNDATION_EXOG + ("gpu", "cpu_fallback"),
        source_declared=True,
        notes="TabICL 2.1.1 checkpoint bytes independently SHA-256 verified in operator evidence",
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-foundation-tabpfn-ts3",
        algorithm_id="tabpfn-ts3",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="priorlabs/tabpfn-ts",
        capabilities=_FOUNDATION_EXOG,
        runtime_status="BLOCKED_INVALID_OR_EXPIRED_TOKEN",
        evidence_class=OPERATOR_LOCAL_EVIDENCE,
        evidence_revision=SKFORECAST_OPERATOR_EVIDENCE_REVISION,
        routability="BLOCKED",
        block_reason="INVALID_OR_EXPIRED_TOKEN",
        notes="adapter contract passed; checkpoint download/inference did not execute",
    ),
    SkforecastImplementationSpec(
        implementation_id="skforecast-foundation-t0",
        algorithm_id="tfc-t0",
        class_name="ForecasterFoundation",
        family="foundation",
        source_alias="theforecastingcompany/t0-alpha",
        capabilities=_FOUNDATION_EXOG,
        evidence_class=OPERATOR_LOCAL_EVIDENCE,
        evidence_revision=SKFORECAST_OPERATOR_EVIDENCE_REVISION,
        notes="not executed in the current skforecast-specific operator sequence",
    ),
)


def skforecast_manifest_count() -> int:
    """Return the deterministic reviewed Phase 4A denominator."""

    return len(SKFORECAST_IMPLEMENTATION_SPECS)
