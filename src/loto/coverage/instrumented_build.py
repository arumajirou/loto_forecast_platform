from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from loto.coverage.instrumented_build_finalize import finalize_build
from loto.coverage.instrumented_common import (
    EXPECTED_COVERAGE_RUNNER_BLOB_SHA,
    absolute,
    count_csv_rows,
    frame_hash,
    make_evidence,
    module,
    run_id,
    source_pin,
)
from loto.coverage.ledger import (
    CoverageLedgerPreflightError,
    CoverageLedgerRecorder,
    require_empty_output,
    require_regular_file,
)


def build_walk_forward(
    *,
    data: Any,
    start: int,
    end: int,
    methods: list[str],
    phase: str,
    recorder: CoverageLedgerRecorder,
    runner_module: Any,
    np_module: Any,
) -> tuple[Any, Any]:
    actual: list[Any] = []
    predicted: list[Any] = []
    experiment_id = "coverage-build-ensemble"
    model_id = "+".join(methods)
    for index in range(start, end):
        fold_id = recorder.register_fold(
            experiment_id=experiment_id,
            model_id=model_id,
            phase=phase,
            test_index=index,
            seed=0,
        )
        history = data[:index]
        points = np_module.vstack(
            [runner_module._point_forecast(history, method) for method in methods]
        )
        prediction = np_module.rint(np_module.median(points, axis=0)).astype(int)
        for position in range(1, prediction.shape[0]):
            prediction[position] = max(prediction[position], prediction[position - 1] + 1)
        recorder.record_prediction(fold_id=fold_id)
        target = data[index].copy()
        recorder.record_actual(fold_id=fold_id)
        actual.append(target)
        predicted.append(prediction)
        recorder.record_score(fold_id=fold_id)
    return np_module.asarray(actual), np_module.asarray(predicted)


def run_coverage_experiment_with_ledger(
    config_path: str | Path,
    *,
    runner_module: Any | None = None,
    pd_module: Any | None = None,
    np_module: Any | None = None,
    canonicalizer: Callable[..., Any] | None = None,
    recorder_factory=CoverageLedgerRecorder,
    clock=None,
    runner_source: str | Path | None = None,
    expected_runner_blob_sha: str = EXPECTED_COVERAGE_RUNNER_BLOB_SHA,
) -> dict[str, Any]:
    runner = runner_module or module("loto.coverage.runner")
    pd = pd_module or module("pandas")
    np = np_module or module("numpy")
    canonicalize = canonicalizer
    if canonicalize is None:
        canonicalize = module("loto.data.canonical").canonicalize_loto7

    config = absolute(config_path)
    require_regular_file(config, label="coverage config")
    raw = runner._load_config(config)
    input_path = absolute(raw.get("data", {})["input"])
    output = absolute(raw.get("output", "runs/coverage-90-ledger"))
    require_regular_file(input_path, label="coverage input")
    root = Path(__file__).resolve().parents[3]
    audited = absolute(runner_source or root / "src/loto/coverage/runner.py")
    source_pin(
        source=audited,
        expected=expected_runner_blob_sha,
        label="coverage runner",
    )
    require_empty_output(output)

    source_total_rows = count_csv_rows(input_path)
    split = raw.get("split", {})
    test_size = int(split.get("test_size", 50))
    calibration_size = int(split.get("calibration_size", 100))
    validation_size = int(split.get("validation_size", 100))
    min_train = int(split.get("min_train_size", 300))
    required = min_train + calibration_size + validation_size + test_size
    if source_total_rows < required:
        raise CoverageLedgerPreflightError(
            f"not enough draws: need {required}, found {source_total_rows}"
        )
    protected_test_start = source_total_rows - test_size
    raw_prefix = pd.read_csv(input_path, nrows=protected_test_start)
    frame, manifest = canonicalize(raw_prefix, source=str(input_path))
    if len(frame) != protected_test_start:
        raise CoverageLedgerPreflightError(
            "canonical prefix row count does not match protected-test boundary"
        )
    data = runner._numbers(frame)
    validation_start = len(data) - validation_size
    calibration_start = validation_start - calibration_size
    if calibration_start < min_train:
        raise CoverageLedgerPreflightError(
            "split leaves fewer than min_train_size accessible draws"
        )

    dataset_sha = str(getattr(manifest, "sha256", frame_hash(frame)))
    data_version = str(getattr(manifest, "data_version", f"coverage-prefix-{dataset_sha[:16]}"))
    evidence = make_evidence(
        frame=frame,
        dataset_id="coverage-loto7-accessible-prefix",
        dataset_sha256=dataset_sha,
        game="loto7",
        source_total_rows=source_total_rows,
        protected_test_start=protected_test_start,
        count=7,
    )
    current_run_id = run_id("coverage-ledger")
    recorder = recorder_factory(
        run_id=current_run_id,
        output_dir=output,
        evidence=evidence,
        expected_seeds=[0],
        clock=clock,
    )
    methods = list(raw.get("models", ["median", "historic-average", "recent-median"]))
    cal_actual, cal_pred = build_walk_forward(
        data=data,
        start=calibration_start,
        end=validation_start,
        methods=methods,
        phase="calibration",
        recorder=recorder,
        runner_module=runner,
        np_module=np,
    )
    val_actual, val_pred = build_walk_forward(
        data=data,
        start=validation_start,
        end=len(data),
        methods=methods,
        phase="validation",
        recorder=recorder,
        runner_module=runner,
        np_module=np,
    )
    return finalize_build(
        raw=raw,
        runner=runner,
        pd=pd,
        np=np,
        output=output,
        recorder=recorder,
        data=data,
        methods=methods,
        cal_actual=cal_actual,
        cal_pred=cal_pred,
        val_actual=val_actual,
        val_pred=val_pred,
        source_total_rows=source_total_rows,
        protected_test_start=protected_test_start,
        calibration_start=calibration_start,
        validation_start=validation_start,
        data_version=data_version,
        current_run_id=current_run_id,
    )
