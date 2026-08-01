from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast
from neuralforecast import models


MODEL_NAMES = [
    "TiDE",
    "TFT",
    "GRU",
    "LSTM",
    "TCN",
    "NBEATSx",
    "NHITS",
    "DeepAR",
    "DilatedRNN",
    "RNN",
    "DLinear",
    "NLinear",
    "MLP",
    "KAN",
    "PatchTST",
    "Autoformer",
    "Informer",
    "VanillaTransformer",
    "iTransformer",
    "TimesNet",
    "StemGNN",
    "BiTCN",
]


def serializable(value: Any) -> Any:
    if value is inspect.Parameter.empty:
        return "__REQUIRED__"

    if isinstance(
        value,
        (str, int, float, bool, type(None)),
    ):
        return value

    return repr(value)


catalog: dict[str, Any] = {
    "neuralforecast_version": getattr(
        neuralforecast,
        "__version__",
        "unknown",
    ),
    "models": {},
}

for model_name in MODEL_NAMES:
    model_class = getattr(models, model_name, None)

    if model_class is None:
        catalog["models"][model_name] = {
            "available": False,
        }
        continue

    signature = inspect.signature(model_class.__init__)
    parameters = {}

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue

        parameters[name] = {
            "kind": str(parameter.kind),
            "default": serializable(parameter.default),
            "annotation": (
                repr(parameter.annotation)
                if parameter.annotation
                is not inspect.Parameter.empty
                else None
            ),
            "required": (
                parameter.default
                is inspect.Parameter.empty
            ),
        }

    catalog["models"][model_name] = {
        "available": True,
        "class": (
            f"{model_class.__module__}."
            f"{model_class.__name__}"
        ),
        "signature": str(signature),
        "parameters": parameters,
    }

out = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_model_parameters.json"
)
out.parent.mkdir(parents=True, exist_ok=True)

out.write_text(
    json.dumps(
        catalog,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print(
    "neuralforecast_version=",
    catalog["neuralforecast_version"],
)

for name, info in catalog["models"].items():
    if not info["available"]:
        print(f"{name:24s} NOT_AVAILABLE")
        continue

    print(
        f"{name:24s}",
        f"parameters={len(info['parameters'])}",
    )

print(f"OUT={out}")
print("MODEL_PARAMETER_INVENTORY=PASS")
