from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.auto as auto_module
import neuralforecast.models as model_module


OUTPUT_JSON = Path("artifacts/parameter_inventory/neuralforecast_auto_model_matrix.json")

OUTPUT_CSV = Path("artifacts/parameter_inventory/neuralforecast_auto_model_matrix.csv")


SPECIAL_NAME_MAP = {
    "AutoAutoformer": "Autoformer",
    "AutoiTransformer": "iTransformer",
}


def parameter_info(
    cls: type[Any],
) -> tuple[set[str], list[str]]:
    signature = inspect.signature(cls.__init__)
    names = set(signature.parameters) - {"self"}

    required = [
        name
        for name, parameter in signature.parameters.items()
        if (
            name != "self"
            and parameter.default is inspect.Parameter.empty
            and parameter.kind
            not in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }
        )
    ]

    return names, required


records = []

for auto_name in sorted(dir(auto_module)):
    if not auto_name.startswith("Auto"):
        continue

    auto_cls = getattr(auto_module, auto_name)

    if not inspect.isclass(auto_cls):
        continue

    base_name = SPECIAL_NAME_MAP.get(
        auto_name,
        auto_name.removeprefix("Auto"),
    )

    model_cls = getattr(
        model_module,
        base_name,
        None,
    )

    if model_cls is None or not inspect.isclass(model_cls):
        records.append(
            {
                "auto_model": auto_name,
                "base_model": base_name,
                "base_model_found": False,
            }
        )
        continue

    parameters, required = parameter_info(model_cls)

    supports_cat = all(
        name in parameters
        for name in (
            "cat_exog_list",
            "categorical_cardinalities",
            "cat_emb_dim",
        )
    )

    records.append(
        {
            "auto_model": auto_name,
            "base_model": base_name,
            "base_model_found": True,
            "future_exog": ("futr_exog_list" in parameters),
            "historical_exog": ("hist_exog_list" in parameters),
            "static_exog": ("stat_exog_list" in parameters),
            "categorical_exog": supports_cat,
            "requires_input_size": ("input_size" in required),
            "accepts_input_size": ("input_size" in parameters),
            "requires_n_series": ("n_series" in required),
            "accepts_n_series": ("n_series" in parameters),
            "accepts_loss": ("loss" in parameters),
            "accepts_valid_loss": ("valid_loss" in parameters),
            "parameter_count": len(parameters),
            "required_parameters": required,
            "model_signature": str(inspect.signature(model_cls.__init__)),
            "auto_signature": str(inspect.signature(auto_cls.__init__)),
        }
    )

OUTPUT_JSON.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_JSON.write_text(
    json.dumps(
        records,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

try:
    import pandas as pd

    pd.DataFrame(records).to_csv(
        OUTPUT_CSV,
        index=False,
    )
except Exception as exc:
    print("WARNING CSV:", repr(exc))

print(
    "auto_classes=",
    len(records),
)

print(
    "mapped_base_models=",
    sum(bool(record.get("base_model_found")) for record in records),
)

print(
    "unmapped=",
    sum(not bool(record.get("base_model_found")) for record in records),
)

print("\n=== UNMAPPED ===")

for record in records:
    if not record.get("base_model_found"):
        print(
            record["auto_model"],
            "->",
            record["base_model"],
        )

print("\nJSON=", OUTPUT_JSON)
print("CSV=", OUTPUT_CSV)
print("AUTO_MODEL_MATRIX=PASS")
