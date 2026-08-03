from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("artifacts/parameter_inventory/neuralforecast_auto_default_spaces.json")

OUTPUT = Path("artifacts/parameter_inventory/neuralforecast_auto_backend_differences.json")


records = json.loads(SOURCE.read_text(encoding="utf-8"))

differences = []

for record in records:
    model = record["auto_model"]

    optuna = record["backends"].get("optuna", {}).get("resolved_config", {})

    ray = record["backends"].get("ray", {}).get("resolved_config", {})

    all_keys = sorted(set(optuna) | set(ray))

    parameter_differences = []

    for key in all_keys:
        optuna_value = optuna.get(
            key,
            "__MISSING__",
        )
        ray_value = ray.get(
            key,
            "__MISSING__",
        )

        if optuna_value != ray_value:
            parameter_differences.append(
                {
                    "parameter": key,
                    "optuna": optuna_value,
                    "ray": ray_value,
                }
            )

    differences.append(
        {
            "auto_model": model,
            "difference_count": len(parameter_differences),
            "differences": parameter_differences,
        }
    )

OUTPUT.write_text(
    json.dumps(
        differences,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

total = sum(record["difference_count"] for record in differences)

for record in differences:
    print(
        f"{record['auto_model']:28s}",
        "differences=",
        record["difference_count"],
    )

print("total_parameter_differences=", total)
print("OUT=", OUTPUT)
print("AUTO_BACKEND_COMPARISON=PASS")
