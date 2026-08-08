from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Any

TARGET_AUTOGLUON_VERSION = "1.5.0"


class InventoryStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class FailureCategory(StrEnum):
    PACKAGE_MISSING = "PACKAGE_MISSING"
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    IMPORT_ERROR = "IMPORT_ERROR"
    SOURCE_CLASS_MISSING = "SOURCE_CLASS_MISSING"
    RUNTIME_ALIAS_MISSING = "RUNTIME_ALIAS_MISSING"
    UNKNOWN_RUNTIME_ALIAS = "UNKNOWN_RUNTIME_ALIAS"
    ENSEMBLE_RESOLUTION_FAILED = "ENSEMBLE_RESOLUTION_FAILED"


@dataclass(frozen=True, slots=True)
class SourceModelSpec:
    alias: str
    class_name: str
    category: str


@dataclass(frozen=True, slots=True)
class SourceEnsembleSpec:
    selectable_name: str
    expected_class_name: str
    alias_of: str | None = None


@dataclass(frozen=True, slots=True)
class InventoryFailure:
    category: FailureCategory
    subject: str
    message: str
    dependency: str | None = None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ModelInventoryEntry:
    alias: str
    class_name: str
    category: str
    source_declared: bool = True
    runtime_discovered: bool = False
    runtime_importable: bool = False
    runtime_certified: bool = False
    runtime_class_name: str | None = None
    failure: InventoryFailure | None = None


@dataclass(frozen=True, slots=True)
class EnsembleInventoryEntry:
    selectable_name: str
    expected_class_name: str
    alias_of: str | None = None
    source_declared: bool = True
    runtime_discovered: bool = False
    runtime_importable: bool = False
    runtime_certified: bool = False
    runtime_class_name: str | None = None
    failure: InventoryFailure | None = None


@dataclass(frozen=True, slots=True)
class AutoGluonRuntimeInventory:
    schema_version: int
    requested_version: str
    installed_version: str | None
    version_matches: bool
    status: InventoryStatus
    models: tuple[ModelInventoryEntry, ...]
    ensembles: tuple[EnsembleInventoryEntry, ...]
    unknown_runtime_model_aliases: tuple[str, ...]
    failures: tuple[InventoryFailure, ...]
    source_model_count: int
    runtime_discovered_model_count: int
    runtime_importable_model_count: int
    runtime_certified_model_count: int
    source_ensemble_name_count: int
    source_unique_ensemble_class_count: int
    runtime_discovered_ensemble_count: int
    runtime_importable_ensemble_count: int
    runtime_certified_ensemble_count: int
    inventory_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("inventory schema_version must equal 1")
        if len(self.inventory_sha256) != 64:
            raise ValueError("inventory_sha256 must contain 64 hexadecimal characters")
        int(self.inventory_sha256, 16)
        expected = {
            "source_model_count": sum(entry.source_declared for entry in self.models),
            "runtime_discovered_model_count": sum(
                entry.runtime_discovered for entry in self.models
            ),
            "runtime_importable_model_count": sum(
                entry.runtime_importable for entry in self.models
            ),
            "runtime_certified_model_count": sum(entry.runtime_certified for entry in self.models),
            "source_ensemble_name_count": sum(entry.source_declared for entry in self.ensembles),
            "source_unique_ensemble_class_count": len(
                {entry.expected_class_name for entry in self.ensembles}
            ),
            "runtime_discovered_ensemble_count": sum(
                entry.runtime_discovered for entry in self.ensembles
            ),
            "runtime_importable_ensemble_count": sum(
                entry.runtime_importable for entry in self.ensembles
            ),
            "runtime_certified_ensemble_count": sum(
                entry.runtime_certified for entry in self.ensembles
            ),
        }
        for field_name, expected_value in expected.items():
            if getattr(self, field_name) != expected_value:
                raise ValueError(
                    f"{field_name}={getattr(self, field_name)} does not match {expected_value}"
                )

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


SOURCE_MODEL_SPECS: tuple[SourceModelSpec, ...] = (
    SourceModelSpec("ADIDA", "ADIDAModel", "intermittent"),
    SourceModelSpec("ARIMA", "ARIMAModel", "statistical"),
    SourceModelSpec("AutoARIMA", "AutoARIMAModel", "statistical"),
    SourceModelSpec("AutoCES", "AutoCESModel", "statistical"),
    SourceModelSpec("AutoETS", "AutoETSModel", "statistical"),
    SourceModelSpec("Average", "AverageModel", "baseline"),
    SourceModelSpec("Croston", "CrostonModel", "intermittent"),
    SourceModelSpec("DLinear", "DLinearModel", "deep_learning"),
    SourceModelSpec("DeepAR", "DeepARModel", "deep_probabilistic"),
    SourceModelSpec("DirectTabular", "DirectTabularModel", "tabular"),
    SourceModelSpec("DynamicOptimizedTheta", "DynamicOptimizedThetaModel", "statistical"),
    SourceModelSpec("ETS", "ETSModel", "statistical"),
    SourceModelSpec("IMAPA", "IMAPAModel", "intermittent"),
    SourceModelSpec("Chronos", "ChronosModel", "foundation"),
    SourceModelSpec("Chronos2", "Chronos2Model", "foundation"),
    SourceModelSpec("NPTS", "NPTSModel", "nonparametric"),
    SourceModelSpec("Naive", "NaiveModel", "baseline"),
    SourceModelSpec("PatchTST", "PatchTSTModel", "deep_learning"),
    SourceModelSpec("PerStepTabular", "PerStepTabularModel", "tabular"),
    SourceModelSpec("RecursiveTabular", "RecursiveTabularModel", "tabular"),
    SourceModelSpec("SeasonalAverage", "SeasonalAverageModel", "baseline"),
    SourceModelSpec("SeasonalNaive", "SeasonalNaiveModel", "baseline"),
    SourceModelSpec("SimpleFeedForward", "SimpleFeedForwardModel", "deep_learning"),
    SourceModelSpec(
        "TemporalFusionTransformer",
        "TemporalFusionTransformerModel",
        "deep_probabilistic",
    ),
    SourceModelSpec("Theta", "ThetaModel", "statistical"),
    SourceModelSpec("TiDE", "TiDEModel", "deep_learning"),
    SourceModelSpec("Toto", "TotoModel", "foundation"),
    SourceModelSpec("WaveNet", "WaveNetModel", "deep_probabilistic"),
    SourceModelSpec("Zero", "ZeroModel", "baseline"),
)

SOURCE_ENSEMBLE_SPECS: tuple[SourceEnsembleSpec, ...] = (
    SourceEnsembleSpec("Greedy", "GreedyEnsemble"),
    SourceEnsembleSpec("PerItemGreedy", "PerItemGreedyEnsemble"),
    SourceEnsembleSpec("PerformanceWeighted", "PerformanceWeightedEnsemble"),
    SourceEnsembleSpec("SimpleAverage", "SimpleAverageEnsemble"),
    SourceEnsembleSpec("Weighted", "GreedyEnsemble", alias_of="Greedy"),
    SourceEnsembleSpec("Median", "MedianEnsemble"),
    SourceEnsembleSpec("Tabular", "TabularEnsemble"),
    SourceEnsembleSpec("PerQuantileTabular", "PerQuantileTabularEnsemble"),
    SourceEnsembleSpec("LinearStacker", "LinearStackerEnsemble"),
)


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _failure_from_exception(subject: str, exc: Exception) -> InventoryFailure:
    if isinstance(exc, importlib.metadata.PackageNotFoundError):
        return InventoryFailure(
            category=FailureCategory.PACKAGE_MISSING,
            subject=subject,
            message=str(exc),
            dependency="autogluon.timeseries",
            error_type=type(exc).__name__,
        )
    if isinstance(exc, ModuleNotFoundError):
        dependency = exc.name
        category = (
            FailureCategory.PACKAGE_MISSING
            if dependency and dependency.startswith("autogluon")
            else FailureCategory.OPTIONAL_DEPENDENCY_MISSING
        )
        return InventoryFailure(
            category=category,
            subject=subject,
            message=str(exc),
            dependency=dependency,
            error_type=type(exc).__name__,
        )
    return InventoryFailure(
        category=FailureCategory.IMPORT_ERROR,
        subject=subject,
        message=str(exc),
        error_type=type(exc).__name__,
    )


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inventory_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_runtime_modules() -> tuple[ModuleType, ModuleType]:
    models_module = importlib.import_module("autogluon.timeseries.models")
    ensemble_module = importlib.import_module("autogluon.timeseries.models.ensemble")
    return models_module, ensemble_module


def _resolve_installed_version() -> str:
    return importlib.metadata.version("autogluon.timeseries")


def discover_runtime_inventory(
    *,
    requested_version: str = TARGET_AUTOGLUON_VERSION,
    models_module: Any | None = None,
    ensemble_module: Any | None = None,
    installed_version: str | None = None,
    version_resolver: Callable[[], str] = _resolve_installed_version,
) -> AutoGluonRuntimeInventory:
    failures: list[InventoryFailure] = []

    if installed_version is None:
        try:
            installed_version = version_resolver()
        except Exception as exc:  # pragma: no cover - concrete exception paths tested
            failures.append(_failure_from_exception("autogluon.timeseries", exc))

    version_matches = installed_version == requested_version
    if installed_version is not None and not version_matches:
        failures.append(
            InventoryFailure(
                category=FailureCategory.VERSION_MISMATCH,
                subject="autogluon.timeseries",
                message=(
                    f"installed version {installed_version!r} does not match "
                    f"requested version {requested_version!r}"
                ),
            )
        )

    if models_module is None or ensemble_module is None:
        try:
            runtime_models, runtime_ensembles = _load_runtime_modules()
            models_module = models_module or runtime_models
            ensemble_module = ensemble_module or runtime_ensembles
        except Exception as exc:
            failures.append(_failure_from_exception("autogluon.timeseries.models", exc))

    runtime_aliases: set[str] = set()
    registry = getattr(models_module, "ModelRegistry", None) if models_module is not None else None
    if registry is not None:
        try:
            runtime_aliases = set(registry.available_aliases())
        except Exception as exc:
            failures.append(_failure_from_exception("ModelRegistry.available_aliases", exc))
    elif models_module is not None:
        failures.append(
            InventoryFailure(
                category=FailureCategory.SOURCE_CLASS_MISSING,
                subject="ModelRegistry",
                message="autogluon.timeseries.models does not expose ModelRegistry",
            )
        )

    model_entries: list[ModelInventoryEntry] = []
    source_aliases = {spec.alias for spec in SOURCE_MODEL_SPECS}
    for spec in SOURCE_MODEL_SPECS:
        runtime_class = getattr(models_module, spec.class_name, None) if models_module else None
        runtime_discovered = spec.alias in runtime_aliases
        failure: InventoryFailure | None = None
        if models_module is not None and runtime_class is None:
            failure = InventoryFailure(
                category=FailureCategory.SOURCE_CLASS_MISSING,
                subject=spec.class_name,
                message=f"source-declared class {spec.class_name!r} is missing at runtime",
            )
        elif registry is not None and not runtime_discovered:
            failure = InventoryFailure(
                category=FailureCategory.RUNTIME_ALIAS_MISSING,
                subject=spec.alias,
                message=f"source-declared alias {spec.alias!r} is absent from runtime registry",
            )
        if failure is not None:
            failures.append(failure)
        model_entries.append(
            ModelInventoryEntry(
                alias=spec.alias,
                class_name=spec.class_name,
                category=spec.category,
                runtime_discovered=runtime_discovered,
                runtime_importable=runtime_class is not None,
                runtime_class_name=(
                    getattr(runtime_class, "__name__", spec.class_name)
                    if runtime_class is not None
                    else None
                ),
                failure=failure,
            )
        )

    unknown_aliases = tuple(sorted(runtime_aliases - source_aliases))
    for alias in unknown_aliases:
        failures.append(
            InventoryFailure(
                category=FailureCategory.UNKNOWN_RUNTIME_ALIAS,
                subject=alias,
                message=f"runtime registry alias {alias!r} is not in the 1.5.0 source manifest",
            )
        )

    ensemble_entries: list[EnsembleInventoryEntry] = []
    get_ensemble_class = (
        getattr(ensemble_module, "get_ensemble_class", None)
        if ensemble_module is not None
        else None
    )
    for spec in SOURCE_ENSEMBLE_SPECS:
        runtime_class: type[Any] | None = None
        failure = None
        if get_ensemble_class is None:
            if ensemble_module is not None:
                failure = InventoryFailure(
                    category=FailureCategory.SOURCE_CLASS_MISSING,
                    subject="get_ensemble_class",
                    message="ensemble module does not expose get_ensemble_class",
                )
        else:
            try:
                runtime_class = get_ensemble_class(spec.selectable_name)
            except Exception as exc:
                failure = InventoryFailure(
                    category=FailureCategory.ENSEMBLE_RESOLUTION_FAILED,
                    subject=spec.selectable_name,
                    message=str(exc),
                    error_type=type(exc).__name__,
                )
        runtime_class_name = getattr(runtime_class, "__name__", None)
        if runtime_class_name is not None and runtime_class_name != spec.expected_class_name:
            failure = InventoryFailure(
                category=FailureCategory.ENSEMBLE_RESOLUTION_FAILED,
                subject=spec.selectable_name,
                message=(
                    f"resolved class {runtime_class_name!r} does not match "
                    f"expected {spec.expected_class_name!r}"
                ),
            )
        if failure is not None:
            failures.append(failure)
        ensemble_entries.append(
            EnsembleInventoryEntry(
                selectable_name=spec.selectable_name,
                expected_class_name=spec.expected_class_name,
                alias_of=spec.alias_of,
                runtime_discovered=runtime_class is not None,
                runtime_importable=runtime_class is not None,
                runtime_class_name=runtime_class_name,
                failure=failure,
            )
        )

    has_package_failure = any(
        failure.category is FailureCategory.PACKAGE_MISSING for failure in failures
    )
    if has_package_failure:
        status = InventoryStatus.ERROR
    elif failures or not version_matches:
        status = InventoryStatus.PARTIAL
    else:
        status = InventoryStatus.OK

    inventory_fields = {
        "schema_version": 1,
        "requested_version": requested_version,
        "installed_version": installed_version,
        "version_matches": version_matches,
        "status": status,
        "models": tuple(model_entries),
        "ensembles": tuple(ensemble_entries),
        "unknown_runtime_model_aliases": unknown_aliases,
        "failures": tuple(failures),
        "source_model_count": len(model_entries),
        "runtime_discovered_model_count": sum(entry.runtime_discovered for entry in model_entries),
        "runtime_importable_model_count": sum(entry.runtime_importable for entry in model_entries),
        "runtime_certified_model_count": sum(entry.runtime_certified for entry in model_entries),
        "source_ensemble_name_count": len(ensemble_entries),
        "source_unique_ensemble_class_count": len(
            {entry.expected_class_name for entry in ensemble_entries}
        ),
        "runtime_discovered_ensemble_count": sum(
            entry.runtime_discovered for entry in ensemble_entries
        ),
        "runtime_importable_ensemble_count": sum(
            entry.runtime_importable for entry in ensemble_entries
        ),
        "runtime_certified_ensemble_count": sum(
            entry.runtime_certified for entry in ensemble_entries
        ),
    }
    serializable_payload = _json_value(inventory_fields)
    return AutoGluonRuntimeInventory(
        **inventory_fields,
        inventory_sha256=_inventory_hash(serializable_payload),
    )


def write_runtime_inventory(
    inventory: AutoGluonRuntimeInventory,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(inventory.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


__all__ = [
    "AutoGluonRuntimeInventory",
    "EnsembleInventoryEntry",
    "FailureCategory",
    "InventoryFailure",
    "InventoryStatus",
    "ModelInventoryEntry",
    "SOURCE_ENSEMBLE_SPECS",
    "SOURCE_MODEL_SPECS",
    "SourceEnsembleSpec",
    "SourceModelSpec",
    "TARGET_AUTOGLUON_VERSION",
    "discover_runtime_inventory",
    "write_runtime_inventory",
]
