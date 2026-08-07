from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import pkgutil
import platform
import sys
from types import ModuleType
from typing import Any

from .inventory import (
    CheckState,
    FormalAvailability,
    InventoryCategory,
    RuntimeInventory,
    RuntimeInventoryEntry,
)

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
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_versions() -> dict[str, Any]:
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


def _signature(value: Any) -> tuple[CheckState, str | None, list[str]]:
    try:
        return CheckState.PASS, str(inspect.signature(value)), []
    except Exception as exc:
        return CheckState.FAIL, None, [f"{type(exc).__name__}: {exc}"]


def _entry_from_export(
    module: ModuleType,
    name: str,
    category: InventoryCategory,
    *,
    expected: bool = True,
) -> RuntimeInventoryEntry:
    value = getattr(module, name, None)
    if value is None:
        return RuntimeInventoryEntry(
            name=name,
            category=category,
            module=module.__name__,
            expected=expected,
            import_state=CheckState.PASS,
            export_state=CheckState.FAIL,
            class_state=CheckState.BLOCKED,
            signature_state=CheckState.BLOCKED,
            formal_availability=FormalAvailability.UNSUPPORTED,
            errors=[f"{module.__name__}.{name} is not exported"],
        )
    if not inspect.isclass(value):
        return RuntimeInventoryEntry(
            name=name,
            category=category,
            module=module.__name__,
            qualname=getattr(value, "__qualname__", None),
            expected=expected,
            import_state=CheckState.PASS,
            export_state=CheckState.PASS,
            class_state=CheckState.FAIL,
            signature_state=CheckState.BLOCKED,
            formal_availability=FormalAvailability.FAILED,
            errors=[f"{module.__name__}.{name} is not a class"],
        )
    signature_state, signature, errors = _signature(value)
    availability = (
        FormalAvailability.DISCOVERED_ONLY
        if signature_state is CheckState.PASS
        else FormalAvailability.EXECUTION_PENDING
    )
    return RuntimeInventoryEntry(
        name=name,
        category=category,
        module=getattr(value, "__module__", module.__name__),
        qualname=getattr(value, "__qualname__", name),
        class_path=(
            f"{getattr(value, '__module__', module.__name__)}."
            f"{getattr(value, '__qualname__', name)}"
        ),
        expected=expected,
        import_state=CheckState.PASS,
        export_state=CheckState.PASS,
        class_state=CheckState.PASS,
        signature_state=signature_state,
        constructor_signature=signature,
        formal_availability=availability,
        errors=errors,
    )


def _failed_entries(
    module_name: str,
    names: tuple[str, ...],
    category: InventoryCategory,
    exc: Exception,
) -> list[RuntimeInventoryEntry]:
    error = f"{type(exc).__name__}: {exc}"
    return [
        RuntimeInventoryEntry(
            name=name,
            category=category,
            module=module_name,
            import_state=CheckState.FAIL,
            export_state=CheckState.BLOCKED,
            class_state=CheckState.BLOCKED,
            signature_state=CheckState.BLOCKED,
            formal_availability=FormalAvailability.EXECUTION_PENDING,
            errors=[error],
        )
        for name in names
    ]


def _expected_class_entries(
    module_name: str,
    names: tuple[str, ...],
    category: InventoryCategory,
) -> list[RuntimeInventoryEntry]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return _failed_entries(module_name, names, category, exc)
    return [_entry_from_export(module, name, category) for name in names]


def _native_predictor_entries() -> list[RuntimeInventoryEntry]:
    module_name = "gluonts.model.predictor"
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return _failed_entries(
            module_name,
            ("Predictor",),
            InventoryCategory.NATIVE_PREDICTOR,
            exc,
        )
    predictor = getattr(module, "Predictor", None)
    if not inspect.isclass(predictor):
        return [_entry_from_export(module, "Predictor", InventoryCategory.NATIVE_PREDICTOR)]
    names = sorted(
        name
        for name, value in vars(module).items()
        if not name.startswith("_")
        and inspect.isclass(value)
        and issubclass(value, predictor)
        and getattr(value, "__module__", "").startswith("gluonts.")
    )
    return [
        _entry_from_export(module, name, InventoryCategory.NATIVE_PREDICTOR, expected=False)
        for name in names
    ]


def _extension_entries() -> list[RuntimeInventoryEntry]:
    module_name = "gluonts.ext"
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return _failed_entries(
            module_name,
            ("gluonts.ext",),
            InventoryCategory.EXTENSION,
            exc,
        )
    paths = getattr(module, "__path__", None)
    if paths is None:
        return [
            RuntimeInventoryEntry(
                name="gluonts.ext",
                category=InventoryCategory.EXTENSION,
                module=module_name,
                expected=False,
                import_state=CheckState.PASS,
                export_state=CheckState.NOT_APPLICABLE,
                class_state=CheckState.NOT_APPLICABLE,
                signature_state=CheckState.NOT_APPLICABLE,
                formal_availability=FormalAvailability.DISCOVERED_ONLY,
            )
        ]
    entries: list[RuntimeInventoryEntry] = []
    for module_info in sorted(pkgutil.iter_modules(paths), key=lambda item: item.name):
        entries.append(
            RuntimeInventoryEntry(
                name=module_info.name,
                category=InventoryCategory.EXTENSION,
                module=f"gluonts.ext.{module_info.name}",
                expected=False,
                import_state=CheckState.NOT_RUN,
                export_state=CheckState.PASS,
                class_state=CheckState.NOT_APPLICABLE,
                signature_state=CheckState.NOT_APPLICABLE,
                formal_availability=FormalAvailability.DISCOVERED_ONLY,
                metadata={"is_package": module_info.ispkg},
            )
        )
    return entries


def discover_runtime_inventory(
    lane: str,
    *,
    include_models: bool = True,
    include_distributions: bool = True,
    include_extensions: bool = True,
) -> RuntimeInventory:
    entries: list[RuntimeInventoryEntry] = []
    if include_models:
        entries.extend(
            _expected_class_entries(
                "gluonts.torch",
                EXPECTED_ESTIMATORS,
                InventoryCategory.PYTORCH_ESTIMATOR,
            )
        )
        entries.extend(_native_predictor_entries())
    if include_extensions:
        entries.extend(_extension_entries())
    if include_distributions:
        entries.extend(
            _expected_class_entries(
                "gluonts.torch.distributions",
                EXPECTED_DISTRIBUTIONS,
                InventoryCategory.DISTRIBUTION_OUTPUT,
            )
        )
    return RuntimeInventory(
        lane=lane,
        runtime_versions=runtime_versions(),
        entries=entries,
    )


def _legacy_discovery(module_name: str, expected_names: tuple[str, ...]) -> dict[str, Any]:
    entries = _expected_class_entries(
        module_name,
        expected_names,
        InventoryCategory.PYTORCH_ESTIMATOR,
    )
    return {
        "module": module_name,
        "module_imported": all(entry.import_state is CheckState.PASS for entry in entries),
        "entries": [
            {
                "name": entry.name,
                "available": entry.export_state is CheckState.PASS,
                "state": entry.formal_availability.value,
                "module": entry.module,
                "qualname": entry.qualname,
            }
            for entry in entries
        ],
        "errors": [error for entry in entries for error in entry.errors],
    }


def discover_models() -> dict[str, Any]:
    return _legacy_discovery("gluonts.torch", EXPECTED_ESTIMATORS)


def discover_distributions() -> dict[str, Any]:
    entries = _expected_class_entries(
        "gluonts.torch.distributions",
        EXPECTED_DISTRIBUTIONS,
        InventoryCategory.DISTRIBUTION_OUTPUT,
    )
    return {
        "module": "gluonts.torch.distributions",
        "module_imported": all(entry.import_state is CheckState.PASS for entry in entries),
        "entries": [
            {
                "name": entry.name,
                "available": entry.export_state is CheckState.PASS,
                "state": entry.formal_availability.value,
                "module": entry.module,
                "qualname": entry.qualname,
            }
            for entry in entries
        ],
        "errors": [error for entry in entries for error in entry.errors],
    }
