from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from loto.auto_campaign import cli


def test_score_command_does_not_load_campaign_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_score(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "PASS", "scoring_id": "score-1"}

    monkeypatch.setattr(cli, "score_locked_prospective_run", fake_score)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _path: (_ for _ in ()).throw(AssertionError("config loaded")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "score-prospective",
            "--run",
            "prospective",
            "--actuals",
            "actuals.csv",
            "--history",
            "history.csv",
            "--output",
            "scoring",
            "--random-seed",
            "7",
            "--actual-source-label",
            "official fixture",
        ],
    )

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert captured["run_root"] == (tmp_path / "prospective").resolve()
    assert captured["actuals_path"] == (tmp_path / "actuals.csv").resolve()
    assert captured["history_path"] == (tmp_path / "history.csv").resolve()
    assert captured["output"] == (tmp_path / "scoring").resolve()
    assert captured["random_seed"] == 7
    assert captured["actual_source_label"] == "official fixture"


def test_verify_scoring_command_is_configless(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "verify_prospective_scoring",
        lambda path: {"status": "PASS", "path": str(path)},
    )
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _path: (_ for _ in ()).throw(AssertionError("config loaded")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "verify-scoring",
            "--run",
            "scoring",
        ],
    )

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["path"] == str((tmp_path / "scoring").resolve())


def test_score_failure_is_structured_and_exits_two(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_kwargs: object) -> dict[str, object]:
        raise ValueError("history mismatch")

    monkeypatch.setattr(cli, "score_locked_prospective_run", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-auto-campaign",
            "--project-root",
            str(tmp_path),
            "score-prospective",
            "--run",
            "prospective",
            "--actuals",
            "actuals.csv",
            "--history",
            "history.csv",
            "--output",
            "scoring",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["error_type"] == "ValueError"
    assert payload["error"] == "history mismatch"
