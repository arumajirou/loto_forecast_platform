from __future__ import annotations

from .contracts import ExpectedStatus, ModelContract

# StatsForecast 2.1.1 public model exports plus the repository's existing CES extension.
# Runtime discovery must compare this fixture with the installed distribution before use.
MODEL_NAMES: tuple[str, ...] = (
    "AutoARIMA",
    "AutoETS",
    "AutoCES",
    "AutoTheta",
    "AutoMFLES",
    "AutoTBATS",
    "ARIMA",
    "AutoRegressive",
    "SimpleExponentialSmoothing",
    "SimpleExponentialSmoothingOptimized",
    "SeasonalExponentialSmoothing",
    "SeasonalExponentialSmoothingOptimized",
    "Holt",
    "HoltWinters",
    "HistoricAverage",
    "Naive",
    "RandomWalkWithDrift",
    "SeasonalNaive",
    "WindowAverage",
    "SeasonalWindowAverage",
    "ADIDA",
    "CrostonClassic",
    "CrostonOptimized",
    "CrostonSBA",
    "IMAPA",
    "TSB",
    "MSTL",
    "MFLES",
    "TBATS",
    "Theta",
    "OptimizedTheta",
    "DynamicTheta",
    "DynamicOptimizedTheta",
    "GARCH",
    "ARCH",
    "SklearnModel",
    "ConstantModel",
    "ZeroModel",
    "NaNModel",
    "UCM",
    "CES",
)

_SEASONAL = {
    "AutoETS",
    "AutoCES",
    "AutoTBATS",
    "SeasonalExponentialSmoothing",
    "SeasonalExponentialSmoothingOptimized",
    "HoltWinters",
    "SeasonalNaive",
    "SeasonalWindowAverage",
    "MSTL",
    "TBATS",
    "CES",
}

_NON_CHAMPION = {"ARCH", "GARCH", "NaNModel", "ConstantModel", "ZeroModel"}


def _contract(name: str) -> ModelContract:
    if name == "NaNModel":
        return ModelContract(
            name=name,
            expected_status=ExpectedStatus.EXPECTED_NEGATIVE_PASS,
            champion_eligible=False,
            capabilities=("negative_non_finite_test",),
            notes="Certification passes only when the finite-value validator rejects output.",
        )
    if name == "SklearnModel":
        return ModelContract(
            name=name,
            expected_status=ExpectedStatus.EXPECTED_DATA_PRECONDITION,
            champion_eligible=True,
            required_parameters=("model",),
            capabilities=("external_estimator", "exogenous"),
        )
    if name in {"ARIMA", "UCM"}:
        return ModelContract(
            name=name,
            expected_status=ExpectedStatus.EXPECTED_DATA_PRECONDITION,
            champion_eligible=True,
            required_parameters=("model_specific_configuration",),
        )
    if name in _SEASONAL:
        return ModelContract(
            name=name,
            expected_status=ExpectedStatus.EXPECTED_DATA_PRECONDITION,
            source="PROJECT_EXTENSION" if name == "CES" else "UPSTREAM_EXPORT",
            champion_eligible=name not in _NON_CHAMPION,
            required_parameters=("season_length", "minimum_two_seasons"),
            capabilities=("seasonal",),
        )
    capabilities: tuple[str, ...] = ()
    if name in {"AutoARIMA", "ARIMA"}:
        capabilities = ("exogenous", "native_intervals", "forward")
    elif name in {"ADIDA", "CrostonClassic", "CrostonOptimized", "CrostonSBA", "IMAPA", "TSB"}:
        capabilities = ("intermittent_demand",)
    elif name in {"ARCH", "GARCH"}:
        capabilities = ("volatility",)
    return ModelContract(
        name=name,
        source="PROJECT_EXTENSION" if name == "CES" else "UPSTREAM_EXPORT",
        champion_eligible=name not in _NON_CHAMPION,
        capabilities=capabilities,
    )


MODEL_CONTRACTS: tuple[ModelContract, ...] = tuple(_contract(name) for name in MODEL_NAMES)
_CONTRACT_BY_NAME = {contract.name: contract for contract in MODEL_CONTRACTS}


def model_contract(name: str) -> ModelContract:
    try:
        return _CONTRACT_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown StatsForecast model: {name}") from exc
