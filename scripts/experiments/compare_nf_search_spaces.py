from __future__ import annotations

import json
from pathlib import Path

import yaml


SPEC = Path(
    "configs/generated/"
    "neuralforecast_complete_search_spec.yaml"
)

DEFAULTS = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_default_spaces.json"
)

OUTPUT = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_search_space_comparison.json"
)


spec = yaml.safe_load(
    SPEC.read_text(encoding="utf-8")
)

defaults = json.loads(
    DEFAULTS.read_text(encoding="utf-8")
)

default_by_model = {
    record["auto_model"]: record
    for record in defaults
}

records = []

for auto_name, model_spec in spec["models"].items():
    custom_common = set(
        model_spec["common_parameter_grid"]
    )

    listed_specific = set(
        model_spec["model_specific_parameters"]
    )

    default_record = default_by_model.get(
        auto_name,
        {},
    )

    optuna_result = (
        default_record
        .get("backends", {})
        .get("optuna", {})
    )

    default_config = optuna_result.get(
        "resolved_config",
        {},
    )

    default_keys = (
        set(default_config)
        if isinstance(default_config, dict)
        else set()
    )

    records.append(
        {
            "auto_model": auto_name,
            "base_model": model_spec["base_model"],
            "default_status": optuna_result.get(
                "status"
            ),
            "official_default_keys": sorted(
                default_keys
            ),
            "custom_common_keys": sorted(
                custom_common
            ),
            "listed_specific_keys": sorted(
                listed_specific
            ),
            "official_not_in_custom": sorted(
                default_keys
                - custom_common
                - listed_specific
                - {
                    "h",
                    "loss",
                    "valid_loss",
                    "futr_exog_list",
                    "hist_exog_list",
                    "stat_exog_list",
                }
            ),
            "custom_not_in_official_default": sorted(
                custom_common - default_keys
            ),
        }
    )

OUTPUT.write_text(
    json.dumps(
        records,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

for record in records:
    print(f"\n=== {record['auto_model']} ===")
    print(
        "default_status=",
        record["default_status"],
    )
    print(
        "official_not_in_custom=",
        record["official_not_in_custom"],
    )
    print(
        "custom_not_in_official_default=",
        record["custom_not_in_official_default"],
    )

print("\nOUT=", OUTPUT)
print("SEARCH_SPACE_COMPARISON=PASS")
