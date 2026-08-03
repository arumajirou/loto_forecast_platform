from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.losses.pytorch as losses
import torch.nn as nn

OUTPUT = Path("artifacts/parameter_inventory/neuralforecast_loss_classification_v2.json")


EXCLUDED_HELPERS = {
    "BaseISQF",
    "BasePointLoss",
    "QuantileLayer",
}

METRICS_ONLY = {
    "Accuracy",
}

POINT_LOSSES = {
    "MAE",
    "MSE",
    "RMSE",
    "HuberLoss",
    "TukeyLoss",
    "MAPE",
    "SMAPE",
    "MASE",
    "RMAE",
    "relMSE",
}

QUANTILE_LOSSES = {
    "QuantileLoss",
    "MQLoss",
    "IQLoss",
    "HuberQLoss",
    "HuberMQLoss",
    "HuberIQLoss",
    "ISQF",
}

DISTRIBUTION_LOSSES = {
    "DistributionLoss",
    "GMM",
    "NBMM",
    "PMM",
    "Tweedie",
    "sCRPS",
}


def classify(
    name: str,
    obj: type[Any],
) -> str:
    if name in EXCLUDED_HELPERS:
        return "base_or_helper"

    if name in METRICS_ONLY:
        return "metric_only"

    if name in POINT_LOSSES:
        return "point"

    if name in QUANTILE_LOSSES:
        return "quantile"

    if name in DISTRIBUTION_LOSSES:
        return "distribution_or_probabilistic"

    if name == "FreDF":
        return "frequency_domain_auxiliary"

    return "manual_review"


records = []

for name in sorted(dir(losses)):
    obj = getattr(losses, name)

    if not inspect.isclass(obj):
        continue

    module = getattr(obj, "__module__", "")

    if not module.startswith("neuralforecast"):
        continue

    category = classify(name, obj)
    signature = inspect.signature(obj.__init__)

    records.append(
        {
            "loss": name,
            "category": category,
            "module": module,
            "is_torch_module": issubclass(obj, nn.Module),
            "signature": str(signature),
            "required_parameters": [
                parameter_name
                for parameter_name, parameter in signature.parameters.items()
                if (
                    parameter_name != "self"
                    and parameter.default is inspect.Parameter.empty
                    and parameter.kind
                    not in {
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    }
                )
            ],
        }
    )

OUTPUT.write_text(
    json.dumps(
        records,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

counts: dict[str, int] = {}

for record in records:
    category = record["category"]
    counts[category] = counts.get(category, 0) + 1

    print(
        f"{record['loss']:28s}",
        f"{category:32s}",
        "required=",
        record["required_parameters"],
    )

print("\n=== COUNTS ===")
for category, count in sorted(counts.items()):
    print(category, count)

print("OUT=", OUTPUT)
print("LOSS_CLASSIFICATION_V2=PASS")
