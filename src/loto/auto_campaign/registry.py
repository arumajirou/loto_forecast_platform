from __future__ import annotations

import inspect
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AutoModelRecord:
    name: str
    module: str
    qualname: str
    signature: str
    track: str
    requires_n_series: bool
    is_hint: bool
    base_model_name: str | None
    exogenous_future: bool | None
    exogenous_historic: bool | None
    exogenous_static: bool | None
    multivariate: bool | None
    supported_backends: tuple[str, ...]
    unsupported_backend_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _track_for(name: str, signature: inspect.Signature) -> str:
    if name == "AutoHINT":
        return "h_hint"
    if "n_series" in signature.parameters:
        return "m_joint"
    return "u_shared_and_local"


def discover_auto_models() -> list[AutoModelRecord]:
    import neuralforecast.auto as auto_module
    from neuralforecast.common._base_auto import BaseAuto

    exported = getattr(auto_module, "__all__", ())
    if not exported:
        raise RuntimeError("neuralforecast.auto.__all__ is empty; refusing heuristic discovery")

    records: list[AutoModelRecord] = []
    false_positives: list[str] = []

    for name in sorted(set(exported)):
        value = getattr(auto_module, name, None)
        if value is None or not inspect.isclass(value):
            if name.startswith("Auto"):
                false_positives.append(name)
            continue
        if value is BaseAuto or not issubclass(value, BaseAuto):
            # neuralforecast.auto.__all__ also exports RayOptions and
            # OptunaOptions. They are legitimate exports, but not AutoModels.
            if name.startswith("Auto"):
                false_positives.append(name)
            continue

        signature = inspect.signature(value)
        base_model = getattr(value, "cls_model", None)
        base_model_name = getattr(base_model, "__name__", None)
        if base_model_name is None:
            try:
                source = inspect.getsource(value)
            except (OSError, TypeError):
                source = ""
            match = re.search(r"cls_model=([A-Za-z_][A-Za-z0-9_]*)", source)
            if match is not None:
                base_model_name = match.group(1)

        # Source inspection is descriptive only and never decides membership.
        attrs = {
            "exogenous_future": getattr(value, "EXOGENOUS_FUTR", None),
            "exogenous_historic": getattr(value, "EXOGENOUS_HIST", None),
            "exogenous_static": getattr(value, "EXOGENOUS_STAT", None),
            "multivariate": getattr(value, "MULTIVARIATE", None),
        }
        records.append(
            AutoModelRecord(
                name=name,
                module=value.__module__,
                qualname=value.__qualname__,
                signature=str(signature),
                track=_track_for(name, signature),
                requires_n_series="n_series" in signature.parameters,
                is_hint=name == "AutoHINT",
                base_model_name=base_model_name,
                supported_backends=("ray",) if name == "AutoHINT" else ("ray", "optuna"),
                unsupported_backend_reason=(
                    "NeuralForecast 3.2.0 rejects backend='optuna' for AutoHINT"
                    if name == "AutoHINT"
                    else None
                ),
                **attrs,
            )
        )

    if false_positives:
        raise RuntimeError(
            f"neuralforecast.auto.__all__ contains non-BaseAuto exports: {false_positives}"
        )  # noqa: E501
    if not records:
        raise RuntimeError("no BaseAuto subclasses discovered")
    return records


def get_auto_class(name: str):
    import neuralforecast.auto as auto_module
    from neuralforecast.common._base_auto import BaseAuto

    cls = getattr(auto_module, name, None)
    if cls is None or not inspect.isclass(cls) or not issubclass(cls, BaseAuto):
        raise ValueError(f"not a registered BaseAuto subclass: {name}")
    return cls


def get_default_config(name: str, *, h: int, backend: str, n_series: int | None) -> Any:
    cls = get_auto_class(name)
    method = getattr(cls, "get_default_config", None)
    if method is None:
        if name == "AutoHINT":
            return None
        raise AttributeError(f"{name} does not expose get_default_config")
    signature = inspect.signature(method)
    kwargs: dict[str, Any] = {}
    if "h" in signature.parameters:
        kwargs["h"] = h
    if "backend" in signature.parameters:
        kwargs["backend"] = backend
    if "n_series" in signature.parameters:
        kwargs["n_series"] = n_series
    return method(**kwargs)
