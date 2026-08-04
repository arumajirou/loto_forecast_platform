from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.auto as auto_module


SOURCE = Path("artifacts/parameter_inventory/full_neuralforecast_search_surface.json")

OUTPUT_JSON = Path("artifacts/parameter_inventory/neuralforecast_auto_model_classification.json")

OUTPUT_CSV = Path("artifacts/parameter_inventory/neuralforecast_auto_model_classification.csv")


def get_required_parameters(
    cls: type[Any],
) -> list[str]:
    signature = inspect.signature(cls.__init__)

    required = []

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue

        if parameter.default is inspect.Parameter.empty and parameter.kind not in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            required.append(name)

    return required


def get_parameter_names(
    cls: type[Any],
) -> set[str]:
    return set(inspect.signature(cls.__init__).parameters) - {"self"}


def classify(
    name: str,
    cls: type[Any],
) -> dict[str, Any]:
    parameters = get_parameter_names(cls)
    required = get_required_parameters(cls)

    underlying = getattr(cls, "_model", None)

    has_default_config = callable(getattr(cls, "get_default_config", None))

    requires_n_series = "n_series" in required
    accepts_n_series = "n_series" in parameters

    hierarchical_markers = {
        "S",
        "cls_model",
        "reconciliation",
    }

    is_hierarchical = bool(hierarchical_markers.intersection(parameters))

    supports_future_exog = "futr_exog_list" in parameters or has_default_config
    supports_historical_exog = "hist_exog_list" in parameters or has_default_config
    supports_static_exog = "stat_exog_list" in parameters or has_default_config

    if name in {"BaseAuto"}:
        category = "base_or_support"
        eligible = False
        exclusion_reason = "Base/support class"

    elif is_hierarchical:
        category = "hierarchical_or_wrapper"
        eligible = False
        exclusion_reason = "Requires hierarchy/reconciliation design"

    elif requires_n_series:
        category = "multivariate"
        eligible = False
        exclusion_reason = "Requires n_series; excluded by current univariate-only policy"

    else:
        category = "univariate_or_global"
        eligible = True
        exclusion_reason = None

    return {
        "auto_model": name,
        "class_module": cls.__module__,
        "class_name": cls.__name__,
        "category": category,
        "eligible_current_policy": eligible,
        "exclusion_reason": exclusion_reason,
        "required_parameters": required,
        "parameter_count": len(parameters),
        "accepts_n_series": accepts_n_series,
        "requires_n_series": requires_n_series,
        "is_hierarchical_or_wrapper": is_hierarchical,
        "has_get_default_config": has_default_config,
        "supports_future_exog_candidate": (supports_future_exog),
        "supports_historical_exog_candidate": (supports_historical_exog),
        "supports_static_exog_candidate": (supports_static_exog),
        "underlying_model_repr": repr(underlying),
        "signature": str(inspect.signature(cls.__init__)),
    }


records = []

for name in sorted(dir(auto_module)):
    if not name.startswith("Auto"):
        continue

    obj = getattr(auto_module, name)

    if not inspect.isclass(obj):
        continue

    records.append(classify(name, obj))

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
    print(
        "WARNING CSV export failed:",
        repr(exc),
    )

counts: dict[str, int] = {}

for record in records:
    category = record["category"]
    counts[category] = counts.get(category, 0) + 1

print("total_auto_classes=", len(records))

for category, count in sorted(counts.items()):
    print(f"{category}={count}")

eligible = [record["auto_model"] for record in records if record["eligible_current_policy"]]

excluded = [
    (
        record["auto_model"],
        record["exclusion_reason"],
    )
    for record in records
    if not record["eligible_current_policy"]
]

print("\n=== ELIGIBLE CURRENT POLICY ===")
for name in eligible:
    print(name)

print("\n=== EXCLUDED OR SEPARATE TRACK ===")
for name, reason in excluded:
    print(name, "->", reason)

print("\nJSON=", OUTPUT_JSON)
print("CSV=", OUTPUT_CSV)
print("AUTO_MODEL_CLASSIFICATION=PASS")
