from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Mapping


CORE_CPU_MODELS = ("Arima", "ETS", "MSES")


@dataclass(frozen=True)
class DiscoveredModel:
    model_name: str
    class_path: str
    task_family: str
    discovery_status: str
    import_status: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _task_family(name: str, class_path: str) -> str:
    if ".anomaly." in class_path:
        return "change_point" if "change_point" in class_path else "anomaly"
    if ".forecast." in class_path:
        return "forecast"
    if ".ensemble." in class_path:
        return "ensemble"
    if ".automl." in class_path:
        return "automl"
    if name.startswith("Default"):
        return "default"
    return "other"


def discover_factory_aliases(
    aliases: Mapping[str, str] | None = None,
) -> list[DiscoveredModel]:
    if aliases is None:
        from merlion.models.factory import import_alias

        aliases = import_alias

    results: list[DiscoveredModel] = []
    for name, class_path in sorted(aliases.items()):
        module_name, separator, attribute = class_path.partition(":")
        if not separator or not module_name or not attribute:
            results.append(
                DiscoveredModel(
                    model_name=name,
                    class_path=class_path,
                    task_family="unknown",
                    discovery_status="DISCOVERED",
                    import_status="FAILED",
                    error="invalid class path",
                )
            )
            continue
        try:
            module = importlib.import_module(module_name)
            getattr(module, attribute)
        except Exception as exc:
            status = "OPTIONAL_DEPENDENCY_MISSING" if isinstance(
                exc, (ImportError, ModuleNotFoundError)
            ) else "FAILED"
            error = f"{type(exc).__name__}: {exc}"
        else:
            status = "IMPORTABLE"
            error = None
        results.append(
            DiscoveredModel(
                model_name=name,
                class_path=class_path,
                task_family=_task_family(name, class_path),
                discovery_status="DISCOVERED",
                import_status=status,
                error=error,
            )
        )
    return results
