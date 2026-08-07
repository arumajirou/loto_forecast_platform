from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.benchmark import ValidationBenchmarkRequest
from loto.sktime_campaign.benchmark_artifacts import (
    BenchmarkVerificationError,
    persist_validation_benchmark,
    verify_validation_benchmark,
)


def request(tmp_path: Path) -> ValidationBenchmarkRequest:
    values = [[float((row + col) % 10) for col in range(3)] for row in range(18)]
    return ValidationBenchmarkRequest.model_validate(
        {
            "output_dir": str(tmp_path / "run"),
            "dataset": {
                "game_id": "numbers3",
                "draw_no": list(range(100, 118)),
                "position_names": ["N1", "N2", "N3"],
                "values": values,
                "legal_min": [0, 0, 0],
                "legal_max": [9, 9, 9],
            },
            "split": {
                "train_rows": 12,
                "validation_rows": 3,
                "holdout_rows": 3,
            },
            "model_ids": [],
            "season_length": 3,
        }
    )


def test_persist_and_verify_baseline_bundle(tmp_path: Path) -> None:
    benchmark_request = request(tmp_path)
    response = persist_validation_benchmark(benchmark_request)
    report = verify_validation_benchmark(
        Path(benchmark_request.output_dir),
        benchmark_request,
        formal=False,
    )
    assert response["status"] == "PASS"
    assert report["status"] == "PASS"
    metadata = json.loads(
        (Path(benchmark_request.output_dir) / "REQUEST_METADATA.json").read_text()
    )
    assert metadata["dataset"]["values"] == "REDACTED_NOT_COPIED_TO_ARTIFACTS"


def test_metric_tamper_fails_even_without_rehash(tmp_path: Path) -> None:
    benchmark_request = request(tmp_path)
    persist_validation_benchmark(benchmark_request)
    results_path = Path(benchmark_request.output_dir) / "CANDIDATE_RESULTS.json"
    rows = json.loads(results_path.read_text())
    rows[0]["metrics"]["hit_at_1"] = 1.0
    results_path.write_text(json.dumps(rows, indent=2) + "\n")
    with pytest.raises(BenchmarkVerificationError, match="metrics mismatch|manifest hash"):
        verify_validation_benchmark(
            Path(benchmark_request.output_dir),
            benchmark_request,
            formal=False,
        )


def test_formal_verification_rejects_missing_model_matrix(tmp_path: Path) -> None:
    benchmark_request = request(tmp_path)
    persist_validation_benchmark(benchmark_request)
    with pytest.raises(BenchmarkVerificationError, match="model inventory mismatch"):
        verify_validation_benchmark(
            Path(benchmark_request.output_dir),
            benchmark_request,
            formal=True,
        )


def test_nonempty_output_directory_fails_closed(tmp_path: Path) -> None:
    benchmark_request = request(tmp_path)
    output = Path(benchmark_request.output_dir)
    output.mkdir(parents=True)
    (output / "stale.txt").write_text("stale")
    with pytest.raises(RuntimeError, match="must be empty"):
        persist_validation_benchmark(benchmark_request)
