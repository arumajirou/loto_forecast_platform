from __future__ import annotations

import importlib
import importlib.metadata
import platform
import sys
from typing import Any

EXPECTED_ESTIMATORS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)

EXPECTED_DISTRIBUTIONS = (
    "BetaOutput",
    "BinnedUniformsOutput",
    "GammaOutput",
    "GeneralizedParetoOutput",
    "ImplicitQuantileNetworkOutput",
    "ISQFOutput",
    "LaplaceOutput",
    "NegativeBinomialOutput",
    "NormalOutput",
    "PiecewiseLinearOutput",
    "PoissonOutput",
    "QuantileOutput",
    "SplicedBinnedParetoOutput",
    "StudentTOutput",
    "TruncatedNormalOutput",
)


def installed_version(package_name: str) -> str | None:
    """Return installed distribution version without importing the package."""

    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_versions() -> dict[str, Any]:
    """Collect provider runtime versions without claiming execution success."""

    return {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "gluonts": installed_version("gluonts"),
        "torch": installed_version("torch"),
        "lightning": installed_version("lightning"),
        "pytorch_lightning": installed_version("pytorch-lightning"),
        "pydantic": installed_version("pydantic"),
    }


def _discover(module_name: str, expected_names: tuple[str, ...]) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return {
            "module": module_name,
            "module_imported": False,
            "entries": [
                {
                    "name": name,
                    "available": False,
                    "state": "IMPORT_FAILED",
                }
                for name in expected_names
            ],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

    entries: list[dict[str, Any]] = []
    for name in expected_names:
        value = getattr(module, name, None)
        entries.append(
            {
                "name": name,
                "available": value is not None,
                "state": "RUNTIME_DISCOVERED" if value is not None else "NOT_EXPORTED",
                "module": getattr(value, "__module__", None),
                "qualname": getattr(value, "__qualname__", None),
            }
        )
    return {
        "module": module_name,
        "module_imported": True,
        "entries": entries,
        "errors": [],
    }


def discover_models() -> dict[str, Any]:
    """Inspect the nine official PyTorch estimator exports without instantiation."""

    return _discover("gluonts.torch", EXPECTED_ESTIMATORS)


def discover_distributions() -> dict[str, Any]:
    """Inspect expected distribution output exports without instantiation."""

    return _discover("gluonts.torch.distributions", EXPECTED_DISTRIBUTIONS)
