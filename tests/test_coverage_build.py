from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from coverage_test_support import (
    FakeRunner,
    PandasProxy,
    SpyRecorder,
    canonicalize_prefix,
    corrupt_protected_rows,
    make_csv,
)
from loto.coverage.instrumented import run_coverage_experiment_with_ledger
from loto.coverage.ledger import CoverageLedgerPreflightError, git_blob_sha


def build_config(tmp_path: Path, input_csv: Path, output: Path) -> Path:
    config = tmp_path / "coverage.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "data": {"input": str(input_csv)},
                "output": str(output),
                "split": {
                    "test_size": 2,
                    "validation_size": 2,
                    "calibration_size": 2,
                    "min_train_size": 8,
                },
                "models": ["median"],
                "coverage": {"target_coverage": 0.9},
            }
        ),
        encoding="utf-8",
    )
    return config


def execute_build(config: Path, source: Path, proxy: PandasProxy):
    return run_coverage_experiment_with_ledger(
        config,
        runner_module=FakeRunner,
        pd_module=proxy,
        np_module=np,
        canonicalizer=canonicalize_prefix,
        recorder_factory=SpyRecorder,
        runner_source=source,
        expected_runner_blob_sha=git_blob_sha(source),
    )


def test_build_reads_only_accessible_prefix_and_orders_hooks(tmp_path: Path) -> None:
    input_csv = tmp_path / "draws.csv"
    make_csv(input_csv)
    output = tmp_path / "out"
    config = build_config(tmp_path, input_csv, output)
    source = tmp_path / "runner.py"
    source.write_text("PIN = True\n", encoding="utf-8")
    proxy = PandasProxy()

    result = execute_build(config, source, proxy)

    assert result["protected_test_materialized"] is False
    assert result["accessible_rows"] == 12
    assert proxy.nrows == [12]
    for fold in {item[1] for item in SpyRecorder.last.log}:
        names = [item[0] for item in SpyRecorder.last.log if item[1] == fold]
        assert names == ["fit", "predict", "actual", "score"]


def test_build_source_pin_blocks_before_output(tmp_path: Path) -> None:
    input_csv = tmp_path / "draws.csv"
    make_csv(input_csv)
    output = tmp_path / "out"
    config = build_config(tmp_path, input_csv, output)
    source = tmp_path / "runner.py"
    source.write_text("PIN = True\n", encoding="utf-8")

    with pytest.raises(CoverageLedgerPreflightError, match="source pin mismatch"):
        run_coverage_experiment_with_ledger(
            config,
            runner_module=FakeRunner,
            pd_module=PandasProxy(),
            np_module=np,
            canonicalizer=canonicalize_prefix,
            recorder_factory=SpyRecorder,
            runner_source=source,
            expected_runner_blob_sha="0" * 40,
        )
    assert not output.exists()


def test_build_does_not_parse_protected_target_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "draws.csv"
    make_csv(input_csv)
    corrupt_protected_rows(input_csv)
    output = tmp_path / "out"
    config = build_config(tmp_path, input_csv, output)
    source = tmp_path / "runner.py"
    source.write_text("PIN = True\n", encoding="utf-8")

    result = execute_build(config, source, PandasProxy())

    assert result["protected_test_materialized"] is False


def test_build_rejects_nonempty_output(tmp_path: Path) -> None:
    input_csv = tmp_path / "draws.csv"
    make_csv(input_csv)
    output = tmp_path / "out"
    output.mkdir()
    (output / "stale.txt").write_text("stale", encoding="utf-8")
    config = build_config(tmp_path, input_csv, output)
    source = tmp_path / "runner.py"
    source.write_text("PIN = True\n", encoding="utf-8")

    with pytest.raises(CoverageLedgerPreflightError, match="empty output"):
        execute_build(config, source, PandasProxy())
