from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from loto.data_access_ledger import AccessOperation

from conftest import make_event, make_ledger


def run_cli(tmp_path: Path, ledger_text: str) -> subprocess.CompletedProcess[str]:
    ledger_path = tmp_path / "ledger.json"
    report_path = tmp_path / "report.json"
    ledger_path.write_text(ledger_text, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).parents[2] / "src")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "loto.data_access_ledger.cli",
            "validate",
            "--ledger",
            str(ledger_path),
            "--report",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_returns_zero_for_valid_ledger(tmp_path: Path) -> None:
    event = make_event(event_id="read", sequence_no=1, operation=AccessOperation.READ)
    ledger = make_ledger([event])
    result = run_cli(tmp_path, ledger.model_dump_json())
    assert result.returncode == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"


def test_cli_returns_one_for_schema_invalid_ledger(tmp_path: Path) -> None:
    result = run_cli(tmp_path, '{"schema_version":"1.0.0"}')
    assert result.returncode == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "INVALID"


def test_cli_returns_two_for_invalid_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "{not-json")
    assert result.returncode == 2
