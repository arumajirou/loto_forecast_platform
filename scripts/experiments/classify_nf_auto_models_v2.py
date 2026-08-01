from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.auto as auto_module
from neuralforecast.common._base_auto import BaseAuto


OUTPUT_JSON = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_model_classification_v2.json"
)

OUTPUT_CSV = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_model_classification_v2.csv"
)


def required_parameters(
    cls: type[Any],
) -> list[str]:
    signature = inspect.signature(cls.__init__)

    return [
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


def parameter_names(
    cls: type[Any],
) -> set[str]:
    return set(
        inspect.signature(cls.__init__).parameters
    ) - {"self"}


records: list[dict[str, Any]] = []
rejected: list[dict[str, str]] = []

for exported_name in sorted(dir(auto_module)):
    if not exported_name.startswith("Auto"):
        continue

    obj = getattr(auto_module, exported_name)

    if not inspect.isclass(obj):
        continue

    if not issubclass(obj, BaseAuto):
        rejected.append(
            {
                "exported_name": exported_name,
                "class_name": obj.__name__,
                "module": obj.__module__,
                "reason": "not_a_BaseAuto_subclass",
            }
        )
        continue

    parameters = parameter_names(obj)
    required = required_parameters(obj)

    hierarchical_markers = {
        "S",
        "cls_model",
        "reconciliation",
    }

    is_hierarchical = bool(
        hierarchical_markers.intersection(parameters)
    )

    requires_n_series = "n_series" in required

    if is_hierarchical:
        category = "hierarchical_or_wrapper"
        eligible = False
        reason = "requires hierarchy/reconciliation"

    elif requires_n_series:
        category = "multivariate"
        eligible = False
        reason = "requires n_series"

    else:
        category = "univariate_or_global"
        eligible = True
        reason = None

    records.append(
        {
            "auto_model": exported_name,
            "class_name": obj.__name__,
            "module": obj.__module__,
            "category": category,
            "eligible_current_policy": eligible,
            "exclusion_reason": reason,
            "required_parameters": required,
            "parameter_count": len(parameters),
            "requires_n_series": requires_n_series,
            "accepts_n_series": "n_series" in parameters,
            "is_hierarchical_or_wrapper": is_hierarchical,
            "has_default_config": callable(
                getattr(obj, "get_default_config", None)
            ),
            "signature": str(
                inspect.signature(obj.__init__)
            ),
        }
    )

payload = {
    "records": records,
    "rejected_exports": rejected,
}

OUTPUT_JSON.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_JSON.write_text(
    json.dumps(
        payload,
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
    print("WARNING CSV export failed:", repr(exc))

counts: dict[str, int] = {}

for record in records:
    category = record["category"]
    counts[category] = counts.get(category, 0) + 1

print("valid_auto_classes=", len(records))
print("rejected_exports=", len(rejected))

for category, count in sorted(counts.items()):
    print(f"{category}={count}")

print("\n=== REJECTED EXPORTS ===")
for record in rejected:
    print(
        record["exported_name"],
        "class=",
        record["class_name"],
        "module=",
        record["module"],
        "reason=",
        record["reason"],
    )

print("\n=== ELIGIBLE ===")
for record in records:
    if record["eligible_current_policy"]:
        print(record["auto_model"])

print("\n=== SEPARATE OR EXCLUDED ===")
for record in records:
    if not record["eligible_current_policy"]:
        print(
            record["auto_model"],
            "->",
            record["exclusion_reason"],
        )

print("JSON=", OUTPUT_JSON)
print("CSV=", OUTPUT_CSV)
print("AUTO_MODEL_CLASSIFICATION_V2=PASS")
