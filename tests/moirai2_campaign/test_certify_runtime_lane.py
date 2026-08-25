from __future__ import annotations

from pathlib import Path

import pytest

from loto.adapters.moirai2.contracts import Moirai2ProviderRequest
from loto.moirai2_campaign.runtime_certification import RuntimeCertificationError
from loto.moirai2_campaign.runtime_preflight import RuntimePreflightError
from scripts import certify_moirai2_runtime as certifier


def _request(snapshot_path: Path) -> Moirai2ProviderRequest:
    return Moirai2ProviderRequest(
        run_id="lane-preflight-test",
        license_lane="personal_noncommercial_research",
        game_geometry={
            "game_id": "numbers3",
            "position_count": 1,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        },
        series_layout="position_univariate",
        position_columns=["n1"],
        history=[{"n1": 1}],
        context_length=1,
        prediction_length=1,
        device="cuda",
        seed=42,
        snapshot_path=str(snapshot_path),
    )


def _lane(tmp_path: Path, *, requires_python: str = ">=3.11,<3.13") -> tuple[Path, Path]:
    lane = tmp_path / "lane"
    lane_python = lane / ".venv" / "bin" / "python"
    lane_python.parent.mkdir(parents=True)
    lane_python.write_text("", encoding="utf-8")
    (lane / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "lane-test"',
                f'requires-python = "{requires_python}"',
                'dependencies = ["uni2ts==2.0.0"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return lane, lane_python


def _install_valid_preflight(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lane: Path,
    lane_python: Path,
    python_version: str = "3.11.14 (main, test)",
    python_executable: Path | None = None,
) -> None:
    monkeypatch.setitem(certifier.RUNTIME_LANES, "cuda13-experimental", lane)
    monkeypatch.setattr(
        certifier,
        "validate_lane_files",
        lambda *args, **kwargs: {
            "lock_sha256": "a" * 64,
            "pyproject_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        certifier,
        "run_frozen_probe",
        lambda **kwargs: {
            "python_executable": str((python_executable or lane_python).absolute()),
            "python_version": python_version,
            "torch_cuda_available": True,
        },
    )


def test_prepare_lane_accepts_exact_frozen_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane, lane_python = _lane(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _install_valid_preflight(monkeypatch, lane=lane, lane_python=lane_python)

    selected, evidence = certifier._prepare_lane_interpreter(
        request=_request(snapshot),
        runtime_lane="cuda13-experimental",
        timeout_seconds=60,
    )

    assert selected == lane_python
    assert evidence["requires_python"] == ">=3.11,<3.13"
    assert evidence["python_version"].startswith("3.11.14")
    assert evidence["python_executable"] == str(lane_python.absolute())


def test_prepare_lane_rejects_stale_python_313(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane, lane_python = _lane(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _install_valid_preflight(
        monkeypatch,
        lane=lane,
        lane_python=lane_python,
        python_version="3.13.1 (main, stale)",
    )

    with pytest.raises(RuntimeCertificationError, match="does not satisfy"):
        certifier._prepare_lane_interpreter(
            request=_request(snapshot),
            runtime_lane="cuda13-experimental",
            timeout_seconds=60,
        )


def test_prepare_lane_rejects_different_existing_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane, lane_python = _lane(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    stale = tmp_path / "stale-venv" / "bin" / "python"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    _install_valid_preflight(
        monkeypatch,
        lane=lane,
        lane_python=lane_python,
        python_executable=stale,
    )

    with pytest.raises(RuntimeCertificationError, match="does not match selected lane"):
        certifier._prepare_lane_interpreter(
            request=_request(snapshot),
            runtime_lane="cuda13-experimental",
            timeout_seconds=60,
        )


def test_prepare_lane_fails_closed_on_frozen_preflight_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane, _ = _lane(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setitem(certifier.RUNTIME_LANES, "cuda13-experimental", lane)

    def fail_preflight(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimePreflightError("lock or installed package mismatch")

    monkeypatch.setattr(certifier, "validate_lane_files", fail_preflight)

    with pytest.raises(RuntimeCertificationError, match="frozen runtime lane preflight failed"):
        certifier._prepare_lane_interpreter(
            request=_request(snapshot),
            runtime_lane="cuda13-experimental",
            timeout_seconds=60,
        )


def test_certify_does_not_start_provider_when_lane_preflight_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lane, _ = _lane(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    request = _request(snapshot)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    monkeypatch.setitem(certifier.RUNTIME_LANES, "cuda13-experimental", lane)
    monkeypatch.setattr(certifier, "RUNNER", tmp_path / "runner.py")
    certifier.RUNNER.write_text("", encoding="utf-8")

    def reject_lane(**kwargs: object) -> tuple[Path, dict[str, object]]:
        raise RuntimeCertificationError("stale lane")

    def provider_must_not_start(**kwargs: object) -> dict[str, object]:
        pytest.fail("provider started before frozen lane preflight passed")

    monkeypatch.setattr(certifier, "_prepare_lane_interpreter", reject_lane)
    monkeypatch.setattr(certifier, "_run_once", provider_must_not_start)

    with pytest.raises(RuntimeCertificationError, match="stale lane"):
        certifier.certify(
            request_path=request_path,
            runtime_lane="cuda13-experimental",
            output_dir=tmp_path / "out",
            timeout_seconds=60,
            monitor_interval_seconds=0.25,
        )