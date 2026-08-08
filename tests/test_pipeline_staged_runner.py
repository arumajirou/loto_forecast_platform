from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.orchestration.pipeline_ledger import (
    PipelineLedgerBlocked,
    PipelineLedgerCloseResult,
)
from loto.orchestration.pipeline_staged import (
    PipelineComponents,
    StagedPipelineBlocked,
    StagedPipelinePreflightError,
    git_blob_sha,
    run_trusted_vertical_slice_staged,
)


class FakeFeatureManifest:
    feature_set_id = "feature-test"

    def model_dump(self, mode="json"):
        return {"feature_set_id": self.feature_set_id}


@dataclass
class FakeCandidate:
    candidate_number: int
    probability: float
    rank_score: float


class FakeForecast:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def model_dump(self, mode="json"):
        result = dict(self.kwargs)
        result["combination"] = {"numbers": list(result["combination"].numbers)}
        result["candidates"] = [vars(item) for item in result["candidates"]]
        for key in ("created_at", "draw_time"):
            result[key] = result[key].isoformat()
        return result


class UniformAdapter:
    model_id = "uniform"

    def fit(self, frame):
        return self

    def predict(self, query):
        numbers = np.arange(1, 38)
        return pd.DataFrame(
            {
                "candidate_number": numbers,
                "probability": np.full(37, 7 / 37),
                "rank_score": np.linspace(1, 0, 37),
            }
        )


class FrequencyAdapter(UniformAdapter):
    model_id = "frequency"

    def predict(self, query):
        frame = super().predict(query)
        frame["rank_score"] = np.linspace(0, 1, 37)
        return frame


class PositionAdapter:
    def fit(self, frame):
        return self

    def predict_matrix(self):
        return np.zeros((7, 37))


class FakeRecorder:
    last = None

    def __init__(self, **kwargs):
        self.log = []
        self.gaps = []
        self.output = kwargs["output_dir"]
        FakeRecorder.last = self

    def register_oof(self, **kwargs):
        self.log.append(("register", kwargs["model_id"], kwargs["fold_id"]))

    def record_oof_prediction(self, **kwargs):
        self.log.append(("predict", kwargs["model_id"], kwargs["fold_id"]))

    def record_oof_actual(self, **kwargs):
        self.log.append(("actual", kwargs["model_id"], kwargs["fold_id"]))

    def record_oof_score(self, **kwargs):
        self.log.append(("score", kwargs["model_id"], kwargs["fold_id"]))

    def record_prospective_prediction(self, **kwargs):
        self.log.append(("prospective", kwargs["model_id"], kwargs["forecast_id"]))

    def record_prediction_lock(self, **kwargs):
        self.log.append(("lock", kwargs["forecast_id"], kwargs["verified"]))
        if not kwargs["verified"]:
            self.gaps.append("FORECAST_SEAL_NOT_VERIFIED")

    def mark_gap(self, code):
        self.gaps.append(code)

    def close(self):
        if self.gaps:
            raise PipelineLedgerBlocked(",".join(self.gaps))
        ledger = self.output / "pipeline_data_access_ledger.json"
        validation = self.output / "pipeline_data_access_validation.json"
        report = self.output / "pipeline_data_access_report.json"
        for path in (ledger, validation, report):
            path.write_text("{}\n", encoding="utf-8")
        return PipelineLedgerCloseResult(
            status="PASS",
            run_id="test",
            ledger_path=ledger,
            validation_path=validation,
            report_path=report,
            ledger_sha256="d" * 64,
            verified_events=len(self.log),
            coverage_gaps=(),
        )


def fake_components(log):
    def canonicalize(frame, source):
        out = frame.copy()
        out["draw_date"] = pd.to_datetime(out["draw_date"], utc=True)
        out.insert(0, "draw_id", out["draw_no"].map(lambda value: f"loto7-{value}"))
        out["available_at"] = out["draw_date"]
        manifest = SimpleNamespace(
            sha256="a" * 64,
            data_version="test-v1",
            dataset_id="loto7-canonical",
        )
        return out, manifest

    def save_manifest(manifest, path):
        Path(path).write_text(
            json.dumps({"sha256": manifest.sha256, "data_version": manifest.data_version}),
            encoding="utf-8",
        )

    def to_candidates(frame):
        return pd.DataFrame({"candidate_number": np.tile(np.arange(1, 38), len(frame))})

    def build_features(frame, windows):
        return pd.DataFrame({"candidate_number": np.arange(1, 38)})

    def build_next(frame, windows):
        return pd.DataFrame({"candidate_number": np.arange(1, 38)})

    def decode(scores, position, top_k):
        values = [1, 2, 3, 4, 5, 6, 7] if scores[0] > scores[-1] else [31, 32, 33, 34, 35, 36, 37]
        return [SimpleNamespace(numbers=values) for _ in range(top_k)]

    def evaluate(actual, predicted):
        log.append("evaluate")
        return {
            "mean_hits_at_7": float(np.mean(actual == predicted)),
            "position_mae": float(np.mean(np.abs(actual - predicted))),
            "position_mse": float(np.mean((actual - predicted) ** 2)),
            "within_1_rate": float(np.mean(np.abs(actual - predicted) <= 1)),
        }

    return PipelineComponents(
        np=np,
        pd=pd,
        canonicalize_loto7=canonicalize,
        save_manifest=save_manifest,
        to_candidate_table=to_candidates,
        build_candidate_features=build_features,
        build_next_candidate_features=build_next,
        feature_manifest=lambda *args: FakeFeatureManifest(),
        UniformCandidateAdapter=UniformAdapter,
        FrequencyCandidateAdapter=FrequencyAdapter,
        PositionFrequencyAdapter=PositionAdapter,
        decode_hybrid=decode,
        evaluate_draws=evaluate,
        brier_score=lambda targets, probabilities: 0.1,
        log_loss=lambda targets, probabilities: 0.2,
        ForecastPackage=FakeForecast,
        CandidateProbability=FakeCandidate,
        seal_payload=lambda payload, secret: {"payload": payload, "mac": "ok"},
        verify_seal=lambda sealed, secret: True,
        collect_gpu_evidence=lambda gpu_required: {"eligible": True},
    )


def make_csv(path: Path) -> None:
    rows = []
    for draw in range(1, 11):
        row = {"draw_no": draw, "draw_date": f"2026-01-{draw:02d}"}
        for index in range(1, 8):
            row[f"n{index}"] = index
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_staged_pipeline_is_ready_without_downstream_side_effects(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    make_csv(input_csv)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    output = tmp_path / "out"
    log = []

    result = run_trusted_vertical_slice_staged(
        input_csv,
        output,
        secret=b"x" * 32,
        backtest_draws=2,
        pipeline_source=source,
        expected_pipeline_blob_sha=git_blob_sha(source),
        components=fake_components(log),
        recorder_factory=FakeRecorder,
        clock=lambda: datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert result["status"] == "READY_FOR_DOWNSTREAM_COMMIT"
    assert result["seal_verified"] is True
    assert (output / "downstream_commit_plan.json").is_file()
    assert not (output / "registry.sqlite3").exists()
    assert not (output / "platform.sqlite3").exists()
    assert not (output / "mlflow_status.json").exists()
    records = FakeRecorder.last.log
    for fold in ("fold-9", "fold-10"):
        positions = {
            name: next(i for i, item in enumerate(records) if item[0] == name and item[2] == fold)
            for name in ("predict", "actual", "score")
        }
        assert positions["predict"] < positions["actual"] < positions["score"]


def test_source_pin_mismatch_blocks_before_output(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    make_csv(input_csv)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    with pytest.raises(StagedPipelinePreflightError, match="source pin mismatch"):
        run_trusted_vertical_slice_staged(
            input_csv,
            tmp_path / "out",
            secret=b"x" * 32,
            pipeline_source=source,
            expected_pipeline_blob_sha="0" * 40,
            components=fake_components([]),
            recorder_factory=FakeRecorder,
        )


def test_nonempty_output_is_rejected(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    make_csv(input_csv)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")
    with pytest.raises(StagedPipelinePreflightError, match="empty output"):
        run_trusted_vertical_slice_staged(
            input_csv,
            output,
            secret=b"x" * 32,
            pipeline_source=source,
            expected_pipeline_blob_sha=git_blob_sha(source),
            components=fake_components([]),
            recorder_factory=FakeRecorder,
        )


def test_short_secret_is_rejected(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    make_csv(input_csv)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    with pytest.raises(StagedPipelinePreflightError, match="16 bytes"):
        run_trusted_vertical_slice_staged(
            input_csv,
            tmp_path / "out",
            secret=b"short",
            pipeline_source=source,
            expected_pipeline_blob_sha=git_blob_sha(source),
            components=fake_components([]),
            recorder_factory=FakeRecorder,
        )


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "input.csv"
    make_csv(real)
    link = tmp_path / "input-link.csv"
    link.symlink_to(real)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    with pytest.raises(StagedPipelinePreflightError, match="symlink"):
        run_trusted_vertical_slice_staged(
            link,
            tmp_path / "out",
            secret=b"x" * 32,
            pipeline_source=source,
            expected_pipeline_blob_sha=git_blob_sha(source),
            components=fake_components([]),
            recorder_factory=FakeRecorder,
        )


def test_unverified_forecast_seal_blocks_staged_pipeline(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    make_csv(input_csv)
    source = tmp_path / "pipeline.py"
    source.write_text("REFERENCE = True\n", encoding="utf-8")
    components = fake_components([])
    components = PipelineComponents(
        **{
            **components.__dict__,
            "verify_seal": lambda sealed, secret: False,
        }
    )
    with pytest.raises(StagedPipelineBlocked, match="FORECAST_SEAL_NOT_VERIFIED"):
        run_trusted_vertical_slice_staged(
            input_csv,
            tmp_path / "out",
            secret=b"x" * 32,
            backtest_draws=1,
            pipeline_source=source,
            expected_pipeline_blob_sha=git_blob_sha(source),
            components=components,
            recorder_factory=FakeRecorder,
            clock=lambda: datetime(2026, 2, 1, tzinfo=UTC),
        )
