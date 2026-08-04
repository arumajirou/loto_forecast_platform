from __future__ import annotations

import inspect
from pathlib import Path

import yaml
from neuralforecast import models

CONFIG = Path("configs/loto7_full_grid_research.yaml")

config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

common = config["common_grid"]
specific = config["model_specific_grid"]

errors = []
warnings = []

for model_name in config["models_stage1"]:
    model_class = getattr(models, model_name, None)

    if model_class is None:
        errors.append(f"{model_name}: model not installed")
        continue

    signature = inspect.signature(model_class.__init__)
    valid = set(signature.parameters)
    has_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )

    requested = {
        *common.keys(),
        *specific.get(model_name, {}).keys(),
    }

    for name in sorted(requested):
        if name in valid:
            continue

        errors.append(f"{model_name}: unsupported or trainer-only argument {name}")

for warning in warnings:
    print("WARNING", warning)

for error in errors:
    print("ERROR", error)

if errors:
    raise SystemExit(1)

forbidden = set(config["experiment"]["forbidden_features"])

selected_columns = {
    column for group in config["feature_groups"].values() for column in group["columns"]
}

leaks = sorted(forbidden & selected_columns)

if leaks:
    raise RuntimeError(f"Forbidden features in grid: {leaks}")

print("GRID_SIGNATURE_VALIDATION=PASS")
