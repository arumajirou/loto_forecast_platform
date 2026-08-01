"""Config loading and the run entry point for the KPI lab."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.game.geometry import geometry_for
from loto.kpi_lab.kpi import CostModel, KpiDefinition
from loto.kpi_lab.metrics import LabMetrics
from loto.kpi_lab.state_machine import KpiLab, LabConfig, LabReport, SearchBudget

__all__ = [
    "load_lab_config",
    "load_draws",
    "run_lab",
    "run_lab_from_config",
]

_ALLOWED_TOP_LEVEL = {"kpi", "budget", "lab", "cost", "data"}


def load_draws(path: str | Path, game: str) -> np.ndarray:
    """Read draw history as an ``(n_draws, positions)`` integer array.

    Column names come from :meth:`GameGeometry.column_names`, so a file for the wrong game
    fails loudly instead of being reinterpreted.
    """
    geometry = geometry_for(game)
    frame = pd.read_csv(path)
    columns = geometry.column_names()
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(
            f"{path}: missing columns {missing} for game={game}; found {list(frame.columns)}"
        )
    values = frame[columns].to_numpy(dtype=np.int64)
    for row in values[: min(len(values), 200)]:
        geometry.validate_outcome([int(v) for v in row])
    return values


def load_lab_config(path: str | Path) -> LabConfig:
    """Parse a YAML lab config. Unknown top-level keys are rejected, not ignored."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path}: config root must be a mapping")
    unknown = set(raw) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise ValueError(
            f"{path}: unknown top-level keys {sorted(unknown)}; "
            f"allowed={sorted(_ALLOWED_TOP_LEVEL)}"
        )
    kpi_raw = dict(raw.get("kpi") or {})
    if "game" not in kpi_raw:
        raise ValueError(f"{path}: kpi.game is required")
    kpi = KpiDefinition(**kpi_raw)
    budget = SearchBudget(**dict(raw.get("budget") or {}))
    lab_raw = dict(raw.get("lab") or {})
    cost_raw = dict(raw.get("cost") or {})
    cost = CostModel(**cost_raw) if cost_raw else CostModel()
    output_dir = Path(lab_raw.pop("output_dir", "artifacts/kpi_lab"))
    return LabConfig(
        kpi=kpi,
        budget=budget,
        output_dir=output_dir,
        cost_model=cost,
        **lab_raw,
    )


def run_lab(
    draws: np.ndarray,
    config: LabConfig,
    *,
    metrics: LabMetrics | None = None,
) -> LabReport:
    """Run one lab session to a terminal state and record metrics."""
    lab = KpiLab(config)
    report = lab.run(draws)
    sink = metrics if metrics is not None else LabMetrics()
    if sink.enabled:
        for record in report.experiments:
            sink.observe_experiment(
                game=config.kpi.game, status=str(record.get("status", "UNKNOWN"))
            )
        if report.reference_arm:
            sink.observe_arm(
                game=config.kpi.game,
                arm="A_reference",
                sealed_coverage=float(report.reference_arm["sealed_coverage"]),
                monte_carlo_coverage=float(report.reference_arm["monte_carlo_coverage"]),
                efficiency=None,
                n_tickets=int(report.reference_arm["n_tickets"]),
            )
        if report.best_model_arm:
            measurement = report.best_measurement or {}
            sink.observe_arm(
                game=config.kpi.game,
                arm="B_model",
                sealed_coverage=float(report.best_model_arm["sealed_coverage"]),
                monte_carlo_coverage=float(report.best_model_arm["monte_carlo_coverage"]),
                efficiency=measurement.get("efficiency"),
                n_tickets=int(report.best_model_arm["n_tickets"]),
            )
        sink.observe_report(report)
        metrics_path = Path(config.output_dir) / report.session_id / "metrics.prom"
        metrics_path.write_bytes(sink.render())
    return report


def run_lab_from_config(
    config_path: str | Path, *, draws_path: str | Path | None = None
) -> dict[str, Any]:
    """CLI-friendly wrapper. Returns the report as a plain dict."""
    config = load_lab_config(config_path)
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    data_cfg = dict(raw.get("data") or {})
    path = draws_path if draws_path is not None else data_cfg.get("draws_path")
    if path is None:
        raise ValueError("no draws path: pass --draws or set data.draws_path in the config")
    draws = load_draws(path, config.kpi.game)
    report = run_lab(draws, config)
    return report.to_dict()
