from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast
import neuralforecast.auto as auto_module
import neuralforecast.models as model_module
import neuralforecast.losses.pytorch as loss_module
from neuralforecast import NeuralForecast
from neuralforecast.common import _base_auto


def encode(value: Any) -> Any:
    if value is inspect.Parameter.empty:
        return "__REQUIRED__"

    if isinstance(
        value,
        (str, int, float, bool, type(None)),
    ):
        return value

    return repr(value)


def signature_info(obj: Any) -> dict[str, Any]:
    try:
        signature = inspect.signature(obj)
    except Exception as exc:
        return {
            "signature_error": repr(exc),
        }

    return {
        "signature": str(signature),
        "parameters": {
            name: {
                "kind": str(parameter.kind),
                "default": encode(parameter.default),
                "annotation": encode(parameter.annotation),
                "required": (
                    parameter.default
                    is inspect.Parameter.empty
                ),
            }
            for name, parameter
            in signature.parameters.items()
        },
    }


report: dict[str, Any] = {
    "neuralforecast_version": getattr(
        neuralforecast,
        "__version__",
        "unknown",
    ),
    "auto_models": {},
    "models": {},
    "losses": {},
    "core": {},
    "auto_support": {},
}

for name in sorted(dir(auto_module)):
    if not name.startswith("Auto"):
        continue

    obj = getattr(auto_module, name)

    if not inspect.isclass(obj):
        continue

    entry = signature_info(obj)

    default_config = getattr(
        obj,
        "default_config",
        None,
    )

    entry["default_config_repr"] = repr(
        default_config
    )

    get_default = getattr(
        obj,
        "get_default_config",
        None,
    )

    entry["has_get_default_config"] = callable(
        get_default
    )

    for backend in ("ray", "optuna"):
        key = f"default_config_{backend}_repr"

        if not callable(get_default):
            entry[key] = None
            continue

        try:
            entry[key] = repr(
                get_default(
                    h=1,
                    backend=backend,
                    n_series=7,
                )
            )
        except TypeError:
            try:
                entry[key] = repr(
                    get_default(
                        h=1,
                        backend=backend,
                    )
                )
            except Exception as exc:
                entry[key] = {
                    "error": repr(exc),
                }
        except Exception as exc:
            entry[key] = {
                "error": repr(exc),
            }

    report["auto_models"][name] = entry

for name in sorted(dir(model_module)):
    obj = getattr(model_module, name)

    if not inspect.isclass(obj):
        continue

    module = getattr(obj, "__module__", "")

    if not module.startswith("neuralforecast"):
        continue

    report["models"][name] = signature_info(obj)

for name in sorted(dir(loss_module)):
    obj = getattr(loss_module, name)

    if not inspect.isclass(obj):
        continue

    module = getattr(obj, "__module__", "")

    if not module.startswith("neuralforecast"):
        continue

    report["losses"][name] = signature_info(obj)

for name in (
    "__init__",
    "fit",
    "predict",
    "cross_validation",
    "save",
    "load",
):
    obj = getattr(NeuralForecast, name, None)

    if obj is not None:
        report["core"][name] = signature_info(obj)

for name in (
    "BaseAuto",
    "RayOptions",
    "OptunaOptions",
):
    obj = getattr(_base_auto, name, None)

    if obj is not None:
        report["auto_support"][name] = signature_info(
            obj
        )

out = Path(
    "artifacts/parameter_inventory/"
    "full_neuralforecast_search_surface.json"
)
out.parent.mkdir(parents=True, exist_ok=True)

out.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print(
    "version=",
    report["neuralforecast_version"],
)
print(
    "auto_models=",
    len(report["auto_models"]),
)
print(
    "models=",
    len(report["models"]),
)
print(
    "losses=",
    len(report["losses"]),
)
print(
    "core_methods=",
    len(report["core"]),
)
print("OUT=", out)
print("FULL_NF_SEARCH_SURFACE=PASS")
