from __future__ import annotations

import inspect
from importlib.metadata import PackageNotFoundError, version
from typing import Any

SELECTED_TAGS: tuple[str, ...] = (
    "capability:pred_int",
    "capability:missing_values",
    "capability:random_state",
    "capability:pretrain",
    "requires-fh-in-fit",
    "fit_is_empty",
    "property:randomness",
    "python_dependencies",
    "python_version",
    "scitype:y",
    "y_inner_mtype",
    "X_inner_mtype",
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if inspect.isclass(value):
        return f"{value.__module__}.{value.__qualname__}"
    return repr(value)


def installed_sktime_version() -> str:
    """Return the installed sktime distribution version."""

    try:
        return version("sktime")
    except PackageNotFoundError as exc:
        raise RuntimeError("sktime distribution is not installed") from exc


def _constructor_signature(cls: type[Any]) -> str:
    try:
        return str(inspect.signature(cls))
    except (TypeError, ValueError):
        return "UNAVAILABLE"


def _class_tags(cls: type[Any]) -> dict[str, Any]:
    try:
        tags = cls.get_class_tags()
    except Exception as exc:  # fail per estimator, not for the complete inventory
        return {"tag_read_error": f"{type(exc).__name__}: {exc}"}
    return {name: _json_safe(tags[name]) for name in SELECTED_TAGS if name in tags}


def _dependency_state(tags: dict[str, Any]) -> str:
    dependencies = tags.get("python_dependencies")
    if dependencies in (None, [], ""):
        return "CORE_COMPATIBLE"
    return "OPTIONAL_DEPENDENCY_DECLARED"


def inventory_rows_from_estimators(
    estimators: list[tuple[str, type[Any]]],
    *,
    package_version: str,
) -> list[dict[str, Any]]:
    """Convert discovered classes into deterministic, JSON-safe inventory rows."""

    rows: list[dict[str, Any]] = []
    for name, cls in sorted(estimators, key=lambda item: item[0]):
        tags = _class_tags(cls)
        rows.append(
            {
                "name": name,
                "class_path": f"{cls.__module__}.{cls.__qualname__}",
                "constructor_signature": _constructor_signature(cls),
                "package_version": package_version,
                "dependency_state": _dependency_state(tags),
                "import_status": "IMPORTABLE",
                "construct_status": "NOT_ATTEMPTED",
                "fit_status": "NOT_ATTEMPTED",
                "predict_status": "NOT_ATTEMPTED",
                "save_load_status": "NOT_ATTEMPTED",
                "tags": tags,
            }
        )
    return rows


def discover_forecasters() -> list[dict[str, Any]]:
    """Discover all public sktime forecasters from the installed runtime."""

    try:
        from sktime.registry import all_estimators
    except Exception as exc:
        raise RuntimeError(f"unable to import sktime registry: {exc}") from exc

    discovered = all_estimators(
        estimator_types="forecaster",
        return_names=True,
        as_dataframe=False,
    )
    estimators: list[tuple[str, type[Any]]] = []
    for item in discovered:
        if not isinstance(item, tuple) or len(item) < 2:
            raise RuntimeError(f"unexpected all_estimators row: {item!r}")
        name, cls = item[0], item[1]
        if not isinstance(name, str) or not inspect.isclass(cls):
            raise RuntimeError(f"invalid all_estimators row: {item!r}")
        estimators.append((name, cls))

    rows = inventory_rows_from_estimators(
        estimators,
        package_version=installed_sktime_version(),
    )
    if not rows:
        raise RuntimeError("sktime registry returned zero forecasters")
    return rows


def summarize_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute counts rather than maintaining hand-written model totals."""

    optional = sum(row["dependency_state"] == "OPTIONAL_DEPENDENCY_DECLARED" for row in rows)
    return {
        "discovered": len(rows),
        "importable": sum(row["import_status"] == "IMPORTABLE" for row in rows),
        "core_compatible": len(rows) - optional,
        "optional_dependency_declared": optional,
        "constructable": 0,
        "runtime_verified": 0,
        "count_source": "sktime.registry.all_estimators('forecaster')",
    }
