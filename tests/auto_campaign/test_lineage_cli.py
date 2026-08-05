from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import cli


class FakeConfig:
    data_path = Path("data.parquet")
    output_root = Path("artifacts")
    campaign_id_prefix = "test"

    def model_copy(self, *, update: dict[str, Any]) -> FakeConfig:
        self.data_path = update["data_path"]
        self.output_root = update["output_root"]
        return self


def test_cli_routes_source_and_predecessor_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "load_config", lambda _path: FakeConfig())
    monkeypatch.setattr(cli, "run_stage_with_promotion_and_lineage", fake_run)
    output = tmp_path / "holdout"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "--config",
            "campaign.yaml",
            "run",
            "--stage",
            "holdout",
            "--source-run",
            "runs/validation",
            "--predecessor-run",
            "runs/oof",
            "--coverage-run",
            "runs/api-coverage",
            "--output",
            str(output),
        ],
    )

    cli.main()

    assert captured["source_run"] == (tmp_path / "runs/validation").resolve()
    assert captured["predecessor_run"] == (tmp_path / "runs/oof").resolve()
    assert captured["coverage_run"] == (tmp_path / "runs/api-coverage").resolve()
    assert captured["runtime_run"] is None
    assert captured["run_root"] == output.resolve()


def test_cli_verify_uses_lineage_aware_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Path] = {}

    def fake_verify(run_root: Path) -> dict[str, Any]:
        captured["run_root"] = run_root
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "load_config", lambda _path: FakeConfig())
    monkeypatch.setattr(cli, "verify_run_with_lineage", fake_verify)
    run_root = tmp_path / "prospective"
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
