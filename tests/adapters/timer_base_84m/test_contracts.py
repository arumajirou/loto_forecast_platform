from __future__ import annotations

import json
import runpy
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from loto.adapters.timer_base_84m.contracts import TimerRequest
from loto.adapters.timer_base_84m.provider import TimerBase84MProvider
from loto.timer_base_84m_campaign.chronology import TimeAxis, validate_chronology
from loto.timer_base_84m_campaign.geometry import Game, geometry_for


def request_payload(*, game: Game = Game.NUMBERS3, context: int = 96) -> dict[str, Any]:
    geometry = geometry_for(game)
    draws = tuple(range(1000, 1000 + context))
    dates = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(context))
    mapping = validate_chronology(
        game=game,
        time_axis=TimeAxis.DRAW_SEQUENCE,
        draw_numbers=draws,
        dates=dates,
        cutoff_draw_no=draws[-1],
        cutoff_date=dates[-1],
        actuals_used=False,
    )
    return {
        "schema_version": "timer-base-84m.request.v1",
        "run_id": "timer-test-0001",
        "operation": "validate_request",
        "model_id": "timer-base-84m",
        "repo_id": "thuml/timer-base-84m",
        "package_version": "4.40.1",
        "source_revision": "UNPINNED",
        "observed_source_head": "1ff8d1afc073182e6d46022069ff32470ab47945",
        "model_revision": "70077a71acce1b4c00d98332fcaabc694255d8e5",
        "config_sha256": "UNVERIFIED",
        "weight_sha256": "9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d",
        "license": "Apache-2.0",
        "game": game,
        "target_layout": "position_univariate",
        "context_length": context,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "input_shape": (geometry.position_count, context),
        "series": tuple(
            tuple(float(index) for index in range(context)) for _ in range(geometry.position_count)
        ),
        "past_covariates": None,
        "known_future_covariates": None,
        "chronology_evidence": {
            "time_axis": TimeAxis.DRAW_SEQUENCE,
            "cutoff_draw_no": draws[-1],
            "cutoff_date": dates[-1],
            "draw_numbers": draws,
            "dates": dates,
            "mapping_sha256": mapping,
            "future_actuals_present": False,
            "duplicate_free": True,
            "strictly_increasing": True,
            "gap_free": True,
        },
        "actuals_used": False,
        "artifact_paths": {
            "request_path": "artifacts/request.json",
            "response_path": "artifacts/response.json",
            "snapshot_path": "snapshots/timer-base-84m",
            "manifest_path": "artifacts/manifest.json",
        },
    }


def json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=lambda value: value.isoformat())


def reject(field: str, value: object) -> None:
    payload = request_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_valid_contract() -> None:
    request = TimerRequest.model_validate(request_payload())
    assert request.input_shape == (3, 96)


def test_strict_json_contract_accepts_canonical_json() -> None:
    request = TimerRequest.model_validate_json(json_payload(request_payload()))
    assert request.game is Game.NUMBERS3
    assert request.chronology_evidence.time_axis is TimeAxis.DRAW_SEQUENCE


def test_unknown_field_rejected() -> None:
    payload = request_payload()
    payload["unknown"] = 1
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", "timer"),
        ("source_revision", "1ff8d1afc073182e6d46022069ff32470ab47945"),
        ("model_revision", "0" * 40),
        ("weight_sha256", "0" * 64),
        ("license", "MIT"),
        ("context_length", 95),
        ("context_length", 2881),
        ("context_length", 97),
        ("prediction_length", 3),
        ("target_layout", "multivariate"),
        ("past_covariates", {"x": [1.0]}),
        ("known_future_covariates", {"x": [1.0]}),
    ],
)
def test_invalid_fields_rejected(field: str, value: object) -> None:
    reject(field, value)


def test_wrong_game_position_count_rejected() -> None:
    payload = request_payload(game=Game.LOTO7)
    payload["series"] = payload["series"][:-1]
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_non_finite_input_rejected() -> None:
    payload = request_payload()
    rows = [list(row) for row in payload["series"]]
    rows[0][0] = float("nan")
    payload["series"] = tuple(tuple(row) for row in rows)
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


@pytest.mark.parametrize("unsafe", ["../weights", ".", "a//b", "a\\b", "./a"])
def test_artifact_path_traversal_rejected(unsafe: str) -> None:
    payload = request_payload()
    payload["artifact_paths"]["snapshot_path"] = unsafe
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_provider_validates_json_without_relaxing_strict_contract(tmp_path) -> None:
    provider = TimerBase84MProvider(tmp_path, tmp_path / "review.json")
    request = provider.validate_request_json(json_payload(request_payload()))
    assert request.source_revision == "UNPINNED"


def test_runner_rejects_operation_mismatch() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = runpy.run_path(str(root / "scripts" / "run_timer_base_84m_provider.py"))
    payload = json.loads(json_payload(request_payload()))
    payload["operation"] = "predict"
    with pytest.raises(ValueError, match="operation mismatch"):
        runner["run"]({"operation": "validate_request", "request": payload})


def test_runner_rejects_unknown_command_field() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = runpy.run_path(str(root / "scripts" / "run_timer_base_84m_provider.py"))
    payload = json.loads(json_payload(request_payload()))
    with pytest.raises(ValueError, match="unknown command fields"):
        runner["run"]({"operation": "validate_request", "request": payload, "unexpected": True})


def test_runner_rejects_unknown_operation() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = runpy.run_path(str(root / "scripts" / "run_timer_base_84m_provider.py"))
    with pytest.raises(ValueError, match="unsupported operation"):
        runner["run"]({"operation": "typo"})


def test_runner_rejects_null_request_on_requestless_operation() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = runpy.run_path(str(root / "scripts" / "run_timer_base_84m_provider.py"))
    with pytest.raises(ValueError, match="must not include a request field"):
        runner["run"]({"operation": "identity", "request": None})


def _run_cli(
    tmp_path: Path,
    payload: dict[str, Any],
) -> tuple[subprocess.CompletedProcess[str], Path]:
    root = Path(__file__).resolve().parents[3]
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_timer_base_84m_provider.py"),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, response_path


def test_cli_success_returns_zero(tmp_path: Path) -> None:
    result, response_path = _run_cli(tmp_path, {"operation": "identity"})
    assert result.returncode == 0
    assert json.loads(response_path.read_text(encoding="utf-8"))["status"] == "IDENTITY"


def test_cli_pending_returns_two(tmp_path: Path) -> None:
    result, response_path = _run_cli(tmp_path, {"operation": "load"})
    assert result.returncode == 2
    assert json.loads(response_path.read_text(encoding="utf-8"))["status"] == (
        "CHECKPOINT_LOAD_PENDING"
    )


def test_cli_invalid_returns_one(tmp_path: Path) -> None:
    result, response_path = _run_cli(tmp_path, {"operation": "typo"})
    assert result.returncode == 1
    assert json.loads(response_path.read_text(encoding="utf-8"))["status"] == "REQUEST_INVALID"


def test_cli_does_not_overwrite_request(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    request_path = tmp_path / "request.json"
    original = '{"operation":"identity"}\n'
    request_path.write_text(original, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_timer_base_84m_provider.py"),
            "--request",
            str(request_path),
            "--response",
            str(request_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert request_path.read_text(encoding="utf-8") == original
    assert "must not overwrite" in result.stderr
