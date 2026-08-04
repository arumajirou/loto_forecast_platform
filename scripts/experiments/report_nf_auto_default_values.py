from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE = Path("artifacts/parameter_inventory/neuralforecast_auto_default_spaces.json")

OUTPUT_CSV = Path("artifacts/parameter_inventory/neuralforecast_auto_default_values.csv")

OUTPUT_MD = Path("artifacts/parameter_inventory/neuralforecast_auto_default_values.md")


def value_type(value: Any) -> str:
    if isinstance(value, list):
        return "candidate_list"

    if isinstance(value, dict):
        return "mapping"

    if isinstance(value, str):
        lowered = value.lower()

        if "suggest_float" in lowered:
            return "continuous_float"

        if "suggest_int" in lowered:
            return "integer_range"

        if "categorical" in lowered:
            return "categorical_repr"

        if "domain" in lowered or "sample" in lowered:
            return "search_domain_repr"

        return "string_or_repr"

    return type(value).__name__


records = json.loads(SOURCE.read_text(encoding="utf-8"))

rows: list[dict[str, Any]] = []

for record in records:
    model = record["auto_model"]

    for backend, backend_result in record["backends"].items():
        status = backend_result["status"]

        if status != "OK":
            rows.append(
                {
                    "auto_model": model,
                    "backend": backend,
                    "parameter": None,
                    "value_type": None,
                    "value": None,
                    "status": status,
                }
            )
            continue

        config = backend_result["resolved_config"]

        for parameter, value in config.items():
            rows.append(
                {
                    "auto_model": model,
                    "backend": backend,
                    "parameter": parameter,
                    "value_type": value_type(value),
                    "value": json.dumps(
                        value,
                        ensure_ascii=False,
                    ),
                    "status": status,
                }
            )

df = pd.DataFrame(rows)

OUTPUT_CSV.parent.mkdir(
    parents=True,
    exist_ok=True,
)

df.to_csv(
    OUTPUT_CSV,
    index=False,
)

summary = (
    df.groupby(
        [
            "auto_model",
            "backend",
        ],
        dropna=False,
    )
    .agg(
        parameter_count=("parameter", "count"),
        value_types=(
            "value_type",
            lambda series: ", ".join(sorted({str(value) for value in series.dropna()})),
        ),
    )
    .reset_index()
)

headers = list(summary.columns)

markdown_lines = [
    "# NeuralForecast Auto Default Values",
    "",
    "| " + " | ".join(headers) + " |",
    "| " + " | ".join("---" for _ in headers) + " |",
]

for row in summary.itertuples(index=False, name=None):
    markdown_lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")

OUTPUT_MD.write_text(
    "\n".join(markdown_lines) + "\n",
    encoding="utf-8",
)

print(summary.to_string(index=False))
print("rows=", len(df))
print("CSV=", OUTPUT_CSV)
print("MD=", OUTPUT_MD)
print("AUTO_DEFAULT_VALUES_REPORT=PASS")
