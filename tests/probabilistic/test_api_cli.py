from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from loto.cli_v3 import main
from loto.probabilistic import api_cli


def test_api_token_create_does_not_print_secret(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "probabilistic",
                "api-token-create",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    target = tmp_path / ".env.ppl-api"
    assert payload["status"] == "CREATED"
    assert payload["token_printed"] is False
    assert payload["token_length"] >= 48
    assert target.is_file()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "LOTO_PPL_API_TOKEN" in target.read_text(encoding="utf-8")
    assert "token" not in payload or payload.get("token") is None


def test_api_health_cli_uses_first_class_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    (tmp_path / ".env.ppl-api").write_text(
        "export LOTO_PPL_API_TOKEN='secret'\n",
        encoding="utf-8",
    )

    def fake_json(self, method, path, **kwargs):  # noqa: ANN001
        assert method == "GET"
        assert path == "/health"
        assert kwargs["authenticated"] is False
        return {"status": "ok", "current_run": None}

    monkeypatch.setattr(api_cli.ApiClient, "json", fake_json)
    assert (
        main(
            [
                "probabilistic",
                "api-health",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_run_start_cli_preserves_eight_worker_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    (tmp_path / ".env.ppl-api").write_text(
        "export LOTO_PPL_API_TOKEN='secret'\n",
        encoding="utf-8",
    )

    def fake_json(self, method, path, **kwargs):  # noqa: ANN001
        payload = kwargs["payload"]
        assert method == "POST"
        assert path == "/api/v1/runs"
        assert payload["overrides"]["outer_workers"] == 8
        assert payload["overrides"]["max_heavy_cpu_jobs"] == 8
        return {"status": "RUNNING", "run_id": "api-test"}

    monkeypatch.setattr(api_cli.ApiClient, "json", fake_json)
    assert (
        main(
            [
                "probabilistic",
                "run-start",
                "--root",
                str(tmp_path),
                "--profile",
                "fast_cpu",
                "--no-preflight",
                "--outer-workers",
                "8",
                "--max-heavy-cpu-jobs",
                "8",
                "--speech-enabled",
                "--no-email-enabled",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["run_id"] == "api-test"
