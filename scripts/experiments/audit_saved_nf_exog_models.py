from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from neuralforecast import NeuralForecast


root = Path(sys.argv[1])
rows: list[dict[str, Any]] = []


def normalize(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (list, tuple, set)):
        return [normalize(item) for item in value]

    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}

    return repr(value)


for properties_path in sorted(root.rglob("model_properties.json")):
    properties = json.loads(properties_path.read_text(encoding="utf-8"))

    model_name = properties["model"]
    condition = properties["condition"]
    saved_path = Path(properties["saved_model_path"])

    record: dict[str, Any] = {
        "model": model_name,
        "condition": condition,
        "saved_model_path": str(saved_path),
        "load_status": "NOT_RUN",
    }

    try:
        nf = NeuralForecast.load(path=str(saved_path))

        if not nf.models:
            raise RuntimeError("Loaded NeuralForecast contains no models")

        model = nf.models[0]

        futr = list(getattr(model, "futr_exog_list", []) or [])
        hist = list(getattr(model, "hist_exog_list", []) or [])
        stat = list(getattr(model, "stat_exog_list", []) or [])

        record.update(
            {
                "load_status": "PASS",
                "loaded_class": (f"{type(model).__module__}.{type(model).__name__}"),
                "alias": getattr(model, "alias", None),
                "h": getattr(model, "h", None),
                "input_size": getattr(
                    model,
                    "input_size",
                    None,
                ),
                "max_steps": getattr(
                    model,
                    "max_steps",
                    None,
                ),
                "scaler_type": getattr(
                    model,
                    "scaler_type",
                    None,
                ),
                "futr_exog_list": futr,
                "hist_exog_list": hist,
                "stat_exog_list": stat,
                "futr_exog_count": len(futr),
                "hist_exog_count": len(hist),
                "stat_exog_count": len(stat),
                "futr_exog_size": getattr(
                    model,
                    "futr_exog_size",
                    None,
                ),
                "hist_exog_size": getattr(
                    model,
                    "hist_exog_size",
                    None,
                ),
                "stat_exog_size": getattr(
                    model,
                    "stat_exog_size",
                    None,
                ),
                "expected_futr": properties.get(
                    "futr_exog_list",
                    [],
                ),
                "expected_hist": properties.get(
                    "hist_exog_list",
                    [],
                ),
                "expected_stat": properties.get(
                    "stat_exog_list",
                    [],
                ),
            }
        )

        record["futr_matches"] = futr == properties.get("futr_exog_list", [])
        record["hist_matches"] = hist == properties.get("hist_exog_list", [])
        record["stat_matches"] = stat == properties.get("stat_exog_list", [])

        record["property_contract_pass"] = all(
            [
                record["futr_matches"],
                record["hist_matches"],
                record["stat_matches"],
            ]
        )

    except Exception as exc:
        record.update(
            {
                "load_status": "FAIL",
                "error": (f"{type(exc).__name__}: {exc}"),
                "property_contract_pass": False,
            }
        )

    rows.append(record)

json_path = root / "saved_model_exog_audit.json"
json_path.write_text(
    json.dumps(
        [normalize(row) for row in rows],
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

flat_rows = []

for row in rows:
    flat_rows.append(
        {
            "model": row["model"],
            "condition": row["condition"],
            "load_status": row["load_status"],
            "loaded_class": row.get("loaded_class"),
            "futr_exog_count": row.get("futr_exog_count"),
            "hist_exog_count": row.get("hist_exog_count"),
            "stat_exog_count": row.get("stat_exog_count"),
            "futr_exog_size": row.get("futr_exog_size"),
            "hist_exog_size": row.get("hist_exog_size"),
            "stat_exog_size": row.get("stat_exog_size"),
            "futr_matches": row.get("futr_matches"),
            "hist_matches": row.get("hist_matches"),
            "stat_matches": row.get("stat_matches"),
            "property_contract_pass": row.get("property_contract_pass"),
            "error": row.get("error"),
        }
    )

df = pd.DataFrame(flat_rows).sort_values(["model", "condition"])

csv_path = root / "saved_model_exog_audit.csv"
df.to_csv(csv_path, index=False)

print(df.to_string(index=False))
print(f"\nJSON={json_path}")
print(f"CSV={csv_path}")

failed = df[(df["load_status"] != "PASS") | (df["property_contract_pass"] != True)]

if not failed.empty:
    print("\nFAILED MODELS")
    print(failed.to_string(index=False))
    raise SystemExit(1)

print("SAVED_MODEL_EXOG_PROPERTY_AUDIT=PASS")
