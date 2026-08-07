from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import cli


def test_cli_exports_without_loading_campaign_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Path] = {}

    def fake_export(run: Path, output: Path) -> dict[str, Any]:
        captured["run"] = run
        captured["output"] = output
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "export_portable_bundle", fake_export)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _path: pytest.fail("portable export must not load campaign config"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "export-portable",
            "--run",
            "runs/prospective",
            "--output",
            "exports/prospective.zip",
        ],
    )

    cli.main()

    assert captured["run"] == (tmp_path / "runs/prospective").resolve()
    assert captured["output"] == (tmp_path / "exports/prospective.zip").resolve()


def test_cli_verifies_bundle_without_loading_campaign_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Path] = {}

    def fake_verify(bundle: Path) -> dict[str, Any]:
        captured["bundle"] = bundle
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "verify_portable_bundle", fake_verify)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _path: pytest.fail("portable verification must not load campaign config"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "verify-portable",
            "--bundle",
            "exports/prospective.zip",
        ],
    )

    cli.main()

    assert captured["bundle"] == (tmp_path / "exports/prospective.zip").resolve()


def test_cli_converts_export_validation_error_to_exit_two(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "export_portable_bundle",
        lambda _run, _output: (_ for _ in ()).throw(ValueError("invalid source seal")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "export-portable",
            "--run",
            "run",
            "--output",
            "bundle.zip",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    payload = capsys.readouterr().out
    assert exc_info.value.code == 2
    assert '"status": "FAIL"' in payload
    assert "invalid source seal" in payload
