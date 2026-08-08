from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.coverage.instrumented import run_auto_research_with_ledger
from loto.coverage.ledger import (
    CoverageLedgerBlocked,
    CoverageLedgerPreflightError,
    git_blob_sha,
)
from tests.coverage_test_support import (
    FakeAuto,
    PandasProxy,
    SpyRecorder,
    auto_config,
    corrupt_protected_rows,
)


def execute_auto(config: Path, source: Path, auto=FakeAuto):
    return run_auto_research_with_ledger(
        config,
        auto_module=auto,
        pd_module=PandasProxy(),
        recorder_factory=SpyRecorder,
        auto_source=source,
        expected_auto_blob_sha=git_blob_sha(source),
    )


def test_auto_research_no_resume_no_llm_and_prefix_only(tmp_path: Path) -> None:
    config, _, output = auto_config(tmp_path)
    source = tmp_path / "auto_research.py"
    source.write_text("PIN = True\n", encoding="utf-8")
    proxy = PandasProxy()

    result = run_auto_research_with_ledger(
        config,
        auto_module=FakeAuto,
        pd_module=proxy,
        recorder_factory=SpyRecorder,
        auto_source=source,
        expected_auto_blob_sha=git_blob_sha(source),
    )

    assert result["status"] == "TARGET_MET_ALL"
    assert result["protected_tests_materialized"] is False
    assert proxy.nrows == [12]
    assert (output / "auto_research_summary.json").is_file()


@pytest.mark.parametrize(
    ("resume", "llm", "message"),
    [
        (True, False, "resume=false"),
        (False, True, "local_llm.enabled=false"),
    ],
)
def test_auto_preflight_rejects_uninstrumented_lanes(
    tmp_path: Path, resume: bool, llm: bool, message: str
) -> None:
    config, _, output = auto_config(tmp_path, resume=resume, llm=llm)
    source = tmp_path / "auto_research.py"
    source.write_text("PIN = True\n", encoding="utf-8")
    with pytest.raises(CoverageLedgerPreflightError, match=message):
        execute_auto(config, source)
    assert not output.exists()


def test_auto_does_not_parse_protected_target_rows(tmp_path: Path) -> None:
    config, input_csv, _ = auto_config(tmp_path)
    corrupt_protected_rows(input_csv)
    source = tmp_path / "auto_research.py"
    source.write_text("PIN = True\n", encoding="utf-8")

    result = execute_auto(config, source)

    assert result["protected_tests_materialized"] is False


def test_auto_experiment_failure_blocks_run(tmp_path: Path) -> None:
    config, _, output = auto_config(tmp_path)
    source = tmp_path / "auto_research.py"
    source.write_text("PIN = True\n", encoding="utf-8")

    class FailingAuto(FakeAuto):
        @staticmethod
        def _point(history, method, params, maximum):
            raise RuntimeError("provider failed")

    with pytest.raises(CoverageLedgerBlocked, match="incomplete experiment evidence"):
        execute_auto(config, source, FailingAuto)
    summary = json.loads((output / "auto_research_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "BLOCKED"
