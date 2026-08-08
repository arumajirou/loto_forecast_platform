from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.data_access_ledger import AccessDecision, DataAccessLedger, validate_ledger
from loto.orchestration.research_ledger_adapter import (
    ResearchDatasetEvidence,
    ResearchLedgerBlocked,
    ResearchLedgerPreflightError,
    run_research_experiment_with_ledger,
)


@dataclass
class Config:
    data: SimpleNamespace
    runtime: SimpleNamespace
    search: SimpleNamespace
    observability: SimpleNamespace


def make_config(tmp_path: Path, **overrides) -> Config:
    source = tmp_path / "draws.csv"
    source.write_text("draw_no,draw_date,n1\n1,2026-01-01,1\n", encoding="utf-8")
    output = tmp_path / "out"
    config = Config(
        data=SimpleNamespace(input=str(source)),
        runtime=SimpleNamespace(output=str(output), resume=False),
        search=SimpleNamespace(backend="none"),
        observability=SimpleNamespace(mlflow_uri=None),
    )
    for path, value in overrides.items():
        target, field = path.split(".")
        setattr(getattr(config, target), field, value)
    return config


def evidence() -> ResearchDatasetEvidence:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return ResearchDatasetEvidence(
        dataset_id="loto7-canonical",
        dataset_sha256="a" * 64,
        data_version="loto7-test-v1",
        game_id="loto7",
        series_ids=tuple(f"n{i}" for i in range(1, 8)),
        observed_times=tuple(base + timedelta(days=index) for index in range(5)),
        draw_ids=tuple(f"loto7-{index + 1}" for index in range(5)),
    )


def successful_runner(config: Config) -> dict:
    output = Path(config.runtime.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "trial_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["model_id", "seed", "status"])
        writer.writeheader()
        writer.writerow({"model_id": "baseline", "seed": 1, "status": "SUCCEEDED"})
    return {
        "run_id": "research-test-run",
        "status": "SUCCEEDED",
        "data_version": "loto7-test-v1",
        "outer_folds": [{"fold_id": "outer-0", "train_end": 3, "test_start": 3, "test_end": 5}],
        "successful_trials": 1,
        "failed_trials": 0,
        "skipped_trials": 0,
    }


def test_adapter_happy_path_writes_valid_ledger(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    summary = run_research_experiment_with_ledger(
        config,
        runner=successful_runner,
        evidence_loader=lambda _: evidence(),
        clock=lambda: datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert summary["data_access_status"] == "PASS"
    output = Path(config.runtime.output)
    ledger = DataAccessLedger.model_validate_json(
        (output / "data_access_ledger.json").read_text(encoding="utf-8")
    )
    report = validate_ledger(ledger)
    assert report.status is AccessDecision.PASS
    assert report.verified_event_count == 7
    adapter = json.loads((output / "data_access_adapter_report.json").read_text())
    assert adapter["runtime_interception"] is False
    assert adapter["coverage_gaps"] == []


@pytest.mark.parametrize(
    ("override", "value", "code"),
    [
        ("search.backend", "optuna", "TUNING_RUNTIME_ACCESS_NOT_INTERCEPTED"),
        ("runtime.resume", True, "RESUME_ARTIFACT_ACCESS_NOT_INTERCEPTED"),
        (
            "observability.mlflow_uri",
            "sqlite:///tracking.db",
            "MLFLOW_WRITE_OCCURS_BEFORE_POST_RUN_VALIDATION",
        ),
    ],
)
def test_preflight_blocks_unintercepted_lanes(
    tmp_path: Path, override: str, value: object, code: str
) -> None:
    config = make_config(tmp_path, **{override: value})
    called = False

    def runner(_: Config) -> dict:
        nonlocal called
        called = True
        return {}

    with pytest.raises(ResearchLedgerPreflightError, match=code):
        run_research_experiment_with_ledger(
            config,
            runner=runner,
            evidence_loader=lambda _: evidence(),
        )
    assert called is False
    report = json.loads(
        (Path(config.runtime.output) / "data_access_adapter_report.json").read_text()
    )
    assert report["status"] == "BLOCKED"
    assert code in report["coverage_gaps"]


def test_failed_trial_blocks_after_evidence_is_written(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    def runner(config: Config) -> dict:
        output = Path(config.runtime.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "trial_results.csv").write_text("model_id,seed,status\n", encoding="utf-8")
        return {
            "run_id": "research-failed",
            "status": "FAILED",
            "data_version": "loto7-test-v1",
            "outer_folds": [
                {
                    "fold_id": "outer-0",
                    "train_end": 3,
                    "test_start": 3,
                    "test_end": 5,
                }
            ],
            "successful_trials": 0,
            "failed_trials": 1,
            "skipped_trials": 0,
        }

    with pytest.raises(ResearchLedgerBlocked, match="FAILED_TRIAL"):
        run_research_experiment_with_ledger(
            config,
            runner=runner,
            evidence_loader=lambda _: evidence(),
        )
    output = Path(config.runtime.output)
    assert (output / "data_access_ledger.json").is_file()
    report = json.loads((output / "data_access_adapter_report.json").read_text())
    assert report["status"] == "BLOCKED"
    assert "FAILED_TRIAL_ACCESS_NOT_FULLY_RECONCILED" in report["coverage_gaps"]


def test_input_mutation_is_detected(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    def runner(config: Config) -> dict:
        Path(config.data.input).write_text("mutated\n", encoding="utf-8")
        return successful_runner(config)

    with pytest.raises(ResearchLedgerBlocked, match="INPUT_CHANGED_DURING_RUN"):
        run_research_experiment_with_ledger(
            config,
            runner=runner,
            evidence_loader=lambda _: evidence(),
        )


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    real = Path(config.data.input)
    link = tmp_path / "input-link.csv"
    link.symlink_to(real)
    config.data.input = str(link)
    with pytest.raises(ResearchLedgerPreflightError, match="symlink"):
        run_research_experiment_with_ledger(
            config,
            runner=successful_runner,
            evidence_loader=lambda _: evidence(),
        )
