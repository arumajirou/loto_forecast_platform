from __future__ import annotations

import json
import sys
from pathlib import Path

from neuralforecast import NeuralForecast

root = Path(sys.argv[1])
output = {}

for properties_path in sorted(root.rglob("model_properties.json")):
    properties = json.loads(properties_path.read_text(encoding="utf-8"))

    key = f"{properties['model']}/{properties['condition']}"

    saved_path = Path(properties["saved_model_path"])
    nf = NeuralForecast.load(path=str(saved_path))
    model = nf.models[0]

    modules = []
    parameters = []

    for name, module in model.named_modules():
        lowered = name.lower()

        if any(
            token in lowered
            for token in (
                "exog",
                "futr",
                "hist",
                "stat",
                "embedding",
                "encoder",
                "decoder",
            )
        ):
            modules.append(
                {
                    "name": name,
                    "class": type(module).__name__,
                }
            )

    for name, parameter in model.named_parameters():
        lowered = name.lower()

        if any(
            token in lowered
            for token in (
                "exog",
                "futr",
                "hist",
                "stat",
                "embedding",
                "encoder",
                "decoder",
            )
        ):
            parameters.append(
                {
                    "name": name,
                    "shape": list(parameter.shape),
                    "trainable": parameter.requires_grad,
                    "numel": parameter.numel(),
                }
            )

    output[key] = {
        "class": type(model).__name__,
        "futr_exog_list": getattr(
            model,
            "futr_exog_list",
            [],
        ),
        "hist_exog_list": getattr(
            model,
            "hist_exog_list",
            [],
        ),
        "stat_exog_list": getattr(
            model,
            "stat_exog_list",
            [],
        ),
        "matching_modules": modules,
        "matching_parameters": parameters,
    }

path = root / "saved_model_structure_audit.json"
path.write_text(
    json.dumps(output, indent=2, default=str),
    encoding="utf-8",
)

for key, value in output.items():
    print(f"\n=== {key} ===")
    print("class=", value["class"])
    print("futr=", value["futr_exog_list"])
    print("hist=", value["hist_exog_list"])
    print("stat=", value["stat_exog_list"])
    print("matching_modules=")

    for module in value["matching_modules"]:
        print(
            " ",
            module["name"],
            module["class"],
        )

print(f"\nOUT={path}")
print("MODEL_STRUCTURE_DUMP=PASS")
