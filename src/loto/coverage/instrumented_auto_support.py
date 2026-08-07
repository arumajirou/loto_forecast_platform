from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.coverage.instrumented_common import count_csv_rows
from loto.coverage.ledger import CoverageLedgerPreflightError


def auto_prefix(
    *,
    input_path: Path,
    game: str,
    game_cfg: dict[str, Any],
    auto_module: Any,
    pd_module: Any,
) -> tuple[Any, int, int, int, int, int]:
    source_total_rows = count_csv_rows(input_path)
    split = game_cfg.get("split", {})
    test_size = int(split.get("test_size", 50))
    validation_size = int(split.get("validation_size", 80))
    calibration_size = int(split.get("calibration_size", 80))
    min_train = int(split.get("min_train_size", 250))
    required = min_train + calibration_size + validation_size + test_size
    if source_total_rows < required:
        raise CoverageLedgerPreflightError(
            f"{game}: need {required} draws, found {source_total_rows}"
        )
    protected_test_start = source_total_rows - test_size
    frame = pd_module.read_csv(input_path, nrows=protected_test_start)
    if "draw_date" in frame.columns:
        frame["draw_date"] = pd_module.to_datetime(
            frame["draw_date"], errors="raise", utc=True
        )
    columns = auto_module._number_columns(frame, game)
    values = frame[columns].apply(
        pd_module.to_numeric, errors="raise"
    ).to_numpy(dtype=int)
    _, maximum = auto_module.GAME_GEOMETRY[game]
    if auto_module.np.any(values < 1) or auto_module.np.any(values > maximum):
        raise CoverageLedgerPreflightError(
            f"{game}: values outside 1..{maximum}"
        )
    if auto_module.np.any(auto_module.np.diff(values, axis=1) <= 0):
        raise CoverageLedgerPreflightError(
            f"{game}: rows must be strictly increasing"
        )
    validation_start = len(values) - validation_size
    calibration_start = validation_start - calibration_size
    if calibration_start < min_train:
        raise CoverageLedgerPreflightError(
            f"{game}: insufficient accessible prefix"
        )
    return (
        frame,
        source_total_rows,
        protected_test_start,
        calibration_start,
        validation_start,
        maximum,
    )


def auto_walk_forward(
    *,
    data: Any,
    start: int,
    end: int,
    proposal: Any,
    maximum: int,
    phase: str,
    recorder: Any,
    auto_module: Any,
) -> tuple[Any, Any]:
    actual: list[Any] = []
    predicted: list[Any] = []
    methods = proposal.ensemble or [proposal.model_id]
    for index in range(start, end):
        fold_id = recorder.register_fold(
            experiment_id=proposal.experiment_id,
            model_id=proposal.model_id,
            phase=phase,
            test_index=index,
            seed=proposal.seed,
        )
        history = data[:index]
        points = [
            auto_module._point(history, method, proposal.params, maximum)
            for method in methods
        ]
        prediction = auto_module._legalize(
            auto_module.np.median(
                auto_module.np.asarray(points), axis=0
            ),
            data.shape[1],
            maximum,
        )
        recorder.record_prediction(fold_id=fold_id)
        target = data[index].copy()
        recorder.record_actual(fold_id=fold_id)
        actual.append(target)
        predicted.append(prediction)
        recorder.record_score(fold_id=fold_id)
    return (
        auto_module.np.asarray(actual, int),
        auto_module.np.asarray(predicted, int),
    )
