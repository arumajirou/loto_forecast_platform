from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import cli
from loto.auto_campaign.coverage_verification import verify_coverage_state_artifacts


def test_noncoverage_run_remains_not_applicable(tmp_path: Path) -> None:
    result = verify_coverage_state_artifacts(
        tmp_path,
        {"schema_version": "all-auto-campaign-run-v1", "status": "PASS"},
    )

    assert result == {
        "applicable": False,
        "status": "NOT_APPLICABLE",
        "coverage_state_status": None,
        "gpu_runtime_status": None,
        "failures": [],
    }


def test_cli_routes_verify_through_coverage_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeConfig:
        data_path = Path("data.parquet")
        output_root = Path("artifacts")

        def model_copy(self, *, update: dict[str, Any]) -> FakeConfig:
            self.data_path = update["data_path"]
            self.output_root = update["output_root"]
            return self

    captured: dict[str, Path] = {}

    def fake_verify(run_root: Path) -> dict[str, Any]:
        captured["run_root"] = run_root
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "load_config", lambda _path: FakeConfig())
    monkeypatch.setattr(cli, "verify_run_with_coverage", fake_verify)
    run_root = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "--config",
            "campaign.yaml",
            "verify",
            "--run",
            str(run_root),
        ],
    )

    cli.main()

    assert captured["run_root"] == run_root.resolve()
