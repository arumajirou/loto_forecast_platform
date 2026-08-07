from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import cli
from loto.auto_campaign.contracts import CampaignConfig, ResourceConfig


def test_cli_routes_hpo_with_resolved_evidence_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = CampaignConfig(
        data_path=Path("data.parquet"),
        output_root=Path("artifacts"),
        resources=ResourceConfig(
            accelerator="gpu",
            gpus_per_trial=0.25,
            gpu_concurrency=1,
        ),
    )
    captured: dict[str, Any] = {}

    def fake_gated_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "run_stage_with_promotion_gate", fake_gated_run)
    output = tmp_path / "runs" / "hpo"
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
            "hpo",
            "--output",
            str(output),
            "--coverage-run",
            "evidence/api-coverage",
            "--runtime-run",
            "evidence/runtime",
        ],
    )

    cli.main()

    assert captured["run_root"] == output.resolve()
    assert captured["coverage_run"] == (tmp_path / "evidence/api-coverage").resolve()
    assert captured["runtime_run"] == (tmp_path / "evidence/runtime").resolve()
    assert captured["source_run"] is None
    assert captured["resume"] is False
    assert captured["runner"] is cli.run_stage


def test_cli_preserves_ungated_smoke_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = CampaignConfig(
        data_path=Path("data.parquet"),
        output_root=Path("artifacts"),
        resources=ResourceConfig(accelerator="cpu", gpus_per_trial=0.0),
    )
    captured: dict[str, Any] = {}

    def fake_run_stage(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "run_stage", fake_run_stage)
    monkeypatch.setattr(
        cli,
        "run_stage_with_promotion_gate",
        lambda **_kwargs: pytest.fail("promotion gate must not run for smoke"),
    )
    output = tmp_path / "smoke"
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
            "smoke",
            "--output",
            str(output),
        ],
    )

    cli.main()

    assert captured["args"][2] == output.resolve()
    assert captured["kwargs"]["source_run"] is None
