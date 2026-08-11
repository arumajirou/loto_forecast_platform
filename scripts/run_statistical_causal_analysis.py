#!/usr/bin/env python
"""Run development-only statistical/causal foundation analysis on a declared CSV snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.analysis.dependence import ljung_box_test, pearson_association, spearman_association
from loto.analysis.multiple_testing import adjust_hypotheses
from loto.analysis.trends import linear_trend, mean_shift_scan
from loto.causal.contracts import IdentificationPlan, assess_identification
from loto.causal.event_study import estimate_pre_post_effect
from loto.causal.negative_control import placebo_event_test

ALLOWED_SCOPES = ("train", "validation", "development")
REPRESENTATIONS = (
    "unordered_draw_feature",
    "sorted_position",
    "draw_aggregate",
    "external_feature",
    "generic_numeric_series",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Development-only trend/dependence/causal-falsification analysis",
    )
    parser.add_argument("--input", required=True, help="CSV snapshot; row order is chronological")
    parser.add_argument("--value-column", required=True)
    parser.add_argument("--association-columns", default="")
    parser.add_argument("--time-column")
    parser.add_argument("--control-column")
    parser.add_argument(
        "--representation", choices=REPRESENTATIONS, default="generic_numeric_series"
    )
    parser.add_argument("--data-scope", choices=ALLOWED_SCOPES, default="development")
    parser.add_argument("--lags", type=int, default=10)
    parser.add_argument("--min-segment", type=int, default=10)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--correction",
        choices=("holm", "benjamini_hochberg"),
        default="benjamini_hochberg",
    )
    parser.add_argument("--event-index", type=int)
    parser.add_argument("--pre-window", type=int, default=20)
    parser.add_argument("--post-window", type=int, default=20)
    parser.add_argument("--max-placebos", type=int, default=200)
    parser.add_argument("--identification-plan", help="JSON file matching IdentificationPlan")
    parser.add_argument("--output", required=True)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _numeric_column(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        raise ValueError(f"column not found: {column}")
    values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    if values.ndim != 1 or values.size < 4 or not np.isfinite(values).all():
        raise ValueError(f"column {column!r} must be a finite numeric series with >= 4 rows")
    return values


def _validate_time_order(frame: pd.DataFrame, column: str | None) -> str:
    if column is None:
        return "csv_row_order_declared_chronological"
    if column not in frame.columns:
        raise ValueError(f"time column not found: {column}")
    parsed = pd.to_datetime(frame[column], errors="raise")
    if parsed.isna().any() or not parsed.is_monotonic_increasing or parsed.duplicated().any():
        raise ValueError("time column must be finite, unique, and monotonically increasing")
    return f"validated_monotonic_time_column:{column}"


def _association_columns(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_identification_plan(path: str | None) -> IdentificationPlan | None:
    if path is None:
        return None
    plan_path = Path(path)
    return IdentificationPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))


def _write_sha256s(output: Path) -> None:
    rows = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{_sha256(path)}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse output directory: {output}")
    output.mkdir(parents=True)

    frame = pd.read_csv(input_path)
    chronology = _validate_time_order(frame, args.time_column)
    values = _numeric_column(frame, args.value_column)
    if args.lags >= len(values) - 1:
        raise ValueError("--lags must be smaller than n - 1")

    trend = linear_trend(values)
    serial = ljung_box_test(values, args.lags)
    change = mean_shift_scan(
        values,
        min_segment=args.min_segment,
        repetitions=args.permutations,
        seed=args.seed,
    )

    associations: list[dict[str, Any]] = []
    hypothesis_ids = ["linear_trend", f"ljung_box_lags_{args.lags}", "max_mean_shift"]
    p_values = [trend.p_value, serial.p_value, change.permutation_p_value]
    for column in _association_columns(args.association_columns):
        other = _numeric_column(frame, column)
        if other.size != values.size:
            raise ValueError(f"association column length mismatch: {column}")
        pearson = pearson_association(values, other, representation=args.representation)
        spearman = spearman_association(values, other, representation=args.representation)
        associations.append(
            {
                "column": column,
                "pearson": pearson.model_dump(mode="json"),
                "spearman": spearman.model_dump(mode="json"),
            }
        )
        hypothesis_ids.extend([f"pearson:{column}", f"spearman:{column}"])
        p_values.extend([pearson.p_value, spearman.p_value])

    adjusted = adjust_hypotheses(
        hypothesis_ids,
        p_values,
        method=args.correction,
        alpha=args.alpha,
    )

    _write_json(output / "TREND.json", trend.model_dump(mode="json"))
    _write_json(output / "SERIAL_DEPENDENCE.json", serial.model_dump(mode="json"))
    _write_json(output / "CHANGE_POINT.json", change.model_dump(mode="json"))
    _write_json(output / "ASSOCIATIONS.json", associations)
    _write_json(
        output / "MULTIPLE_TESTING.json",
        [item.model_dump(mode="json") for item in adjusted],
    )

    plan = _load_identification_plan(args.identification_plan)
    identification = assess_identification(plan) if plan is not None else None
    event_payload: dict[str, Any] | None = None
    placebo_payload: dict[str, Any] | None = None
    final_causal_gate = False
    if args.event_index is not None:
        control = _numeric_column(frame, args.control_column) if args.control_column else None
        event = estimate_pre_post_effect(
            values,
            event_index=args.event_index,
            pre_window=args.pre_window,
            post_window=args.post_window,
            control_values=control,
            identification_plan=plan,
        )
        placebo = placebo_event_test(
            values,
            event_index=args.event_index,
            pre_window=args.pre_window,
            post_window=args.post_window,
            control_values=control,
            max_placebos=args.max_placebos,
            seed=args.seed,
            alpha=args.alpha,
        )
        event_payload = event.model_dump(mode="json")
        placebo_payload = placebo.model_dump(mode="json")
        final_causal_gate = event.causal_claim_eligible and placebo.falsification_passed
        _write_json(output / "EVENT_EFFECT.json", event_payload)
        _write_json(output / "PLACEBO_FALSIFICATION.json", placebo_payload)

    config = {
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "value_column": args.value_column,
        "association_columns": _association_columns(args.association_columns),
        "time_column": args.time_column,
        "chronology": chronology,
        "control_column": args.control_column,
        "representation": args.representation,
        "data_scope": args.data_scope,
        "lags": args.lags,
        "min_segment": args.min_segment,
        "permutations": args.permutations,
        "seed": args.seed,
        "alpha": args.alpha,
        "correction": args.correction,
        "event_index": args.event_index,
        "pre_window": args.pre_window,
        "post_window": args.post_window,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
    }
    _write_json(output / "CONFIG.json", config)
    summary = {
        "status": "ANALYSIS_COMPLETE",
        "rows": int(len(values)),
        "representation": args.representation,
        "data_scope": args.data_scope,
        "hypotheses_in_family": len(hypothesis_ids),
        "multiplicity_correction": args.correction,
        "identification": (
            identification.model_dump(mode="json") if identification is not None else None
        ),
        "event_effect": event_payload,
        "placebo_falsification": placebo_payload,
        "causal_evidence_gate": final_causal_gate,
        "causal_gate_interpretation": (
            "eligible for guarded downstream causal interpretation; not proof of causality"
            if final_causal_gate
            else "causal claim remains closed"
        ),
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
    }
    _write_json(output / "SUMMARY.json", summary)
    _write_sha256s(output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
