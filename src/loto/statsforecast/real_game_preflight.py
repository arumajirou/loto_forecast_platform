"""Repository-native StatsForecast real-game constructor preflight.

The preflight is intentionally narrower than forecasting accuracy evaluation. It proves
that every catalogued StatsForecast model can be constructed through the same certified
parameter resolver used by Phase C, while preserving the semantic UNIVARIATE / EXOGENOUS /
EXPECTED_NEGATIVE_CONTROL lane assignment for all 41 inventory rows.
"""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from loto.models.catalog_full import ModelEntry, build_catalog

from .certification_io import write_json, write_manifest_and_sums
from .real_game_runtime import RealGameLane, lane_for_model, resolve_entry_parameters


def statsforecast_entries() -> list[ModelEntry]:
    """Return the complete broad-catalog StatsForecast inventory in stable order."""

    return [entry for entry in build_catalog() if entry.library == "statsforecast"]


def build_preflight_matrix(
    entries: Sequence[Any],
    models_module: Any,
) -> list[dict[str, Any]]:
    """Construct every supplied StatsForecast entry and retain fail-visible evidence."""

    rows: list[dict[str, Any]] = []
    for entry in entries:
        lane = lane_for_model(entry.class_name)
        row: dict[str, Any] = {
            "model_id": entry.model_id,
            "model_name": entry.class_name,
            "lane": lane.value,
            "primary_univariate_eligible": lane is RealGameLane.UNIVARIATE,
            "construct_status": "EXECUTION_FAILED",
        }
        try:
            parameters = resolve_entry_parameters(entry, models_module)
            model_class = getattr(models_module, entry.class_name)
            model_class(**parameters)
            row.update(
                {
                    "construct_status": "VERIFIED",
                    "resolved_parameter_names": sorted(parameters),
                    "resolved_parameters": parameters,
                    "error_type": None,
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - preflight rows must remain fail-visible
            row.update(
                {
                    "resolved_parameter_names": [],
                    "resolved_parameters": {},
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        rows.append(row)
    return rows


def summarize_preflight(
    rows: Sequence[dict[str, Any]],
    *,
    expected_model_count: int,
    expected_univariate: int,
    expected_exogenous: int,
    expected_negative_control: int,
    statsforecast_version: str,
) -> dict[str, Any]:
    """Summarize one preflight using explicit inventory expectations."""

    verified = sum(row["construct_status"] == "VERIFIED" for row in rows)
    failed = len(rows) - verified
    lane_counts = {
        lane.value: sum(row["lane"] == lane.value for row in rows) for lane in RealGameLane
    }
    failed_models = [
        {
            "model_id": row["model_id"],
            "model_name": row["model_name"],
            "error_type": row.get("error_type"),
            "error": row.get("error"),
        }
        for row in rows
        if row["construct_status"] != "VERIFIED"
    ]
    formal_pass = bool(
        len(rows) == expected_model_count
        and verified == expected_model_count
        and failed == 0
        and lane_counts[RealGameLane.UNIVARIATE.value] == expected_univariate
        and lane_counts[RealGameLane.EXOGENOUS.value] == expected_exogenous
        and lane_counts[RealGameLane.EXPECTED_NEGATIVE_CONTROL.value] == expected_negative_control
        and not failed_models
    )
    return {
        "schema_version": 1,
        "library": "statsforecast",
        "statsforecast_version": statsforecast_version,
        "model_count": len(rows),
        "construct_verified": verified,
        "construct_failed": failed,
        "lane_counts": lane_counts,
        "failed_models": failed_models,
        "formal_pass": formal_pass,
    }


def run_real_game_preflight(
    output_dir: Path,
    *,
    entries: Sequence[Any] | None = None,
    models_module: Any | None = None,
    statsforecast_version: str | None = None,
) -> dict[str, Any]:
    """Run the canonical 41-model constructor/lane preflight and write evidence."""

    if output_dir.exists():
        raise FileExistsError(f"refusing to reuse preflight output directory: {output_dir}")
    output_dir.mkdir(parents=True)

    if entries is None:
        entries = statsforecast_entries()
    if models_module is None:
        models_module = importlib.import_module("statsforecast.models")
    if statsforecast_version is None:
        statsforecast = importlib.import_module("statsforecast")
        statsforecast_version = str(statsforecast.__version__)

    rows = build_preflight_matrix(entries, models_module)
    summary = summarize_preflight(
        rows,
        expected_model_count=41,
        expected_univariate=39,
        expected_exogenous=1,
        expected_negative_control=1,
        statsforecast_version=statsforecast_version,
    )
    write_json(output_dir / "REAL_GAME_PREFLIGHT_MATRIX.json", rows)
    write_json(output_dir / "REAL_GAME_PREFLIGHT_SUMMARY.json", summary)
    write_manifest_and_sums(output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify StatsForecast Phase C constructor and lane readiness."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    summary = run_real_game_preflight(args.output_dir)
    print(f"OUTPUT_DIR={args.output_dir}")
    print(f"MODEL_COUNT={summary['model_count']}")
    print(f"CONSTRUCT_VERIFIED={summary['construct_verified']}")
    print(f"CONSTRUCT_FAILED={summary['construct_failed']}")
    print(f"LANE_COUNTS={summary['lane_counts']}")
    print(f"FORMAL_PASS={str(summary['formal_pass']).lower()}")
    return 0 if summary["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_preflight_matrix",
    "main",
    "run_real_game_preflight",
    "statsforecast_entries",
    "summarize_preflight",
]
