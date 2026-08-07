from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import yaml

from loto.coverage.ledger import (
    CoverageLedgerBlocked,
    CoverageLedgerCloseResult,
)


class PandasProxy:
    DataFrame = pd.DataFrame
    to_numeric = staticmethod(pd.to_numeric)
    to_datetime = staticmethod(pd.to_datetime)

    def __init__(self) -> None:
        self.nrows: list[int | None] = []

    def read_csv(self, path, nrows=None):
        self.nrows.append(nrows)
        return pd.read_csv(path, nrows=nrows)


class SpyRecorder:
    last = None

    def __init__(self, **kwargs):
        self.output = kwargs["output_dir"]
        self.log: list[tuple] = []
        self.gaps: list[str] = []
        SpyRecorder.last = self

    def register_fold(self, **kwargs):
        fold_id = f"{kwargs['phase']}-{kwargs['test_index']}-{kwargs['model_id']}"
        self.log.append(("fit", fold_id))
        return fold_id

    def record_prediction(self, *, fold_id):
        self.log.append(("predict", fold_id))

    def record_actual(self, *, fold_id):
        self.log.append(("actual", fold_id))

    def record_score(self, *, fold_id):
        self.log.append(("score", fold_id))

    def mark_gap(self, code):
        self.gaps.append(code)

    def close(self):
        if self.gaps:
            raise CoverageLedgerBlocked(",".join(self.gaps))
        self.output.mkdir(parents=True, exist_ok=True)
        ledger = self.output / "coverage_data_access_ledger.json"
        validation = self.output / "coverage_data_access_validation.json"
        report = self.output / "coverage_data_access_report.json"
        for path in (ledger, validation, report):
            path.write_text("{}\n", encoding="utf-8")
        return CoverageLedgerCloseResult(
            status="PASS",
            run_id="test",
            ledger_path=ledger,
            validation_path=validation,
            report_path=report,
            ledger_sha256="d" * 64,
            verified_events=len(self.log),
            coverage_gaps=(),
        )


class Eval:
    row_within_tolerance = 1.0

    def to_dict(self):
        return {"row_within_tolerance": self.row_within_tolerance}


class PredictionSet:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def to_dict(self):
        return self.kwargs


class CoverageConfig:
    def __init__(self, **kwargs):
        self.target_coverage = float(kwargs.get("target_coverage", 0.9))
        self.calibration_margin = float(kwargs.get("calibration_margin", 0.02))
        self.tolerance = int(kwargs.get("tolerance", 1))
        self.per_position_top = 2
        self.beam_width = 20
        self.pool_size = 20
        self.max_candidates = 3
        self.diversity_penalty = 0.0


class FakeRunner:
    CoverageConfig = CoverageConfig
    PredictionSet = PredictionSet

    @staticmethod
    def _load_config(path):
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _numbers(frame):
        return frame[[f"n{i}" for i in range(1, 8)]].to_numpy(dtype=int)

    @staticmethod
    def _point_forecast(history, method):
        return np.rint(np.median(history, axis=0)).astype(int)

    @staticmethod
    def simultaneous_conformal_radius(*args):
        return 1

    @staticmethod
    def position_probabilities(data, center):
        return np.ones((7, 37))

    @staticmethod
    def generate_candidate_pool(*args, **kwargs):
        return [tuple(range(1, 8)), tuple(range(2, 9))]

    @staticmethod
    def augment_with_residual_offsets(*args, **kwargs):
        return []

    @staticmethod
    def greedy_coverage_select(actual, pool, **kwargs):
        return pool[:1], [{"coverage": 1.0}]

    @staticmethod
    def evaluate_candidates(actual, selected, tolerance):
        return Eval()


@dataclass(frozen=True)
class Budget:
    max_experiments: int = 1
    max_runtime_seconds: int = 60
    max_consecutive_failures: int = 1
    max_candidates: int = 5
    target_coverage: float = 0.9
    calibration_margin: float = 0.02
    tolerance: int = 1
    stop_when_target_met: bool = True


@dataclass(frozen=True)
class Proposal:
    experiment_id: str = "proposal-1"
    game: str = "loto7"
    model_id: str = "median"
    params: dict | None = None
    ensemble: list | None = None
    pool_size: int = 5
    per_position_top: int = 2
    beam_width: int = 20
    diversity_penalty: float = 0.0
    seed: int = 1
    source: str = "grid"

    def __post_init__(self):
        object.__setattr__(self, "params", self.params or {})
        object.__setattr__(self, "ensemble", self.ensemble or [])

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "game": self.game,
            "model_id": self.model_id,
            "params": self.params,
            "ensemble": self.ensemble,
            "pool_size": self.pool_size,
            "seed": self.seed,
        }


class FakeAuto:
    np = np
    GAME_GEOMETRY = {"loto7": (7, 37)}
    SearchBudget = Budget

    @staticmethod
    def _load_yaml(path):
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _number_columns(frame, game):
        return [f"n{i}" for i in range(1, 8)]

    @staticmethod
    def build_grid(raw, game):
        return [Proposal()]

    @staticmethod
    def _point(history, method, params, maximum):
        return tuple(np.rint(np.median(history, axis=0)).astype(int))

    @staticmethod
    def _legalize(row, count, maximum):
        return tuple(np.rint(np.asarray(row)).astype(int).tolist())

    @staticmethod
    def _candidate_pool(center, residuals, count, maximum, proposal):
        return [tuple(range(1, 8)), tuple(range(2, 9))]

    @staticmethod
    def _greedy_general(actual, pool, **kwargs):
        return pool[:1], [{"coverage": 1.0}]

    @staticmethod
    def _evaluate_general(actual, candidates, tolerance):
        return {"row_within_tolerance": 1.0, "mean_best_mae": 0.0}


def make_csv(path: Path, rows: int = 14) -> None:
    records = []
    for draw in range(1, rows + 1):
        record = {"draw_no": draw, "draw_date": f"2026-01-{draw:02d}"}
        for index in range(1, 8):
            record[f"n{index}"] = index
        records.append(record)
    pd.DataFrame(records).to_csv(path, index=False)


def canonicalize_prefix(frame, source):
    result = frame.copy()
    result["draw_date"] = pd.to_datetime(result["draw_date"], utc=True)
    result.insert(
        0,
        "draw_id",
        result["draw_no"].map(lambda value: f"loto7-{value}"),
    )
    return result, SimpleNamespace(sha256="a" * 64, data_version="prefix-v1")


def corrupt_protected_rows(path: Path, protected: int = 2) -> None:
    frame = pd.read_csv(path, dtype=str)
    for row in range(len(frame) - protected, len(frame)):
        frame.loc[row, "n1"] = "PROTECTED-NOT-PARSED"
    frame.to_csv(path, index=False)


def auto_config(tmp_path: Path, *, resume=False, llm=False):
    input_csv = tmp_path / "draws.csv"
    make_csv(input_csv)
    output = tmp_path / "auto-out"
    config = tmp_path / "auto.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "output": str(output),
                "resume": resume,
                "local_llm": {"enabled": llm},
                "budget": {"max_experiments": 1},
                "games": {
                    "loto7": {
                        "input": str(input_csv),
                        "split": {
                            "test_size": 2,
                            "validation_size": 2,
                            "calibration_size": 2,
                            "min_train_size": 8,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return config, input_csv, output
