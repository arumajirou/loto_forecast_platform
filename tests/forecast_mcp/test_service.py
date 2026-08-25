from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from loto.adapters.moirai2.contracts import (
    GpuEvidence,
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
    RuntimeEvidence,
)
from loto.forecast_mcp.contracts import ForecastMcpConfig, ForecastToolRequest
from loto.forecast_mcp.service import ForecastMcpService
from loto.gpu_exclusive.models import ExternalGateConfig, GpuProbeConfig, HttpRuntimeConfig
from loto.moirai2_campaign.model_manifest import MODEL_ID, MODEL_REVISION, REPO_ID


def _write_approved_request(tmp_path: Path) -> tuple[Path, Path]:
    request = Moirai2ProviderRequest(
        run_id="approved-template",
        license_lane="personal_noncommercial_research",
        game_geometry={
            "game_id": "numbers3",
            "position_count": 3,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        },
        series_layout="position_multivariate",
        position_columns=["n1", "n2", "n3"],
        history=[
            {"n1": index % 10, "n2": (index + 3) % 10, "n3": (index + 7) % 10}
            for index in range(128)
        ],
        context_length=128,
        prediction_length=1,
        device="cuda",
        seed=1,
        local_files_only=True,
    )
    request_path = tmp_path / "numbers3-development-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    request_sha = hashlib.sha256(request_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "numbers3-development-request.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "data_scope": "development",
                "actuals_used": False,
                "holdout_used": False,
                "prospective_used": False,
                "request_sha256": request_sha,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return request_path, manifest_path


def _config(tmp_path: Path) -> ForecastMcpConfig:
    request_path, manifest_path = _write_approved_request(tmp_path)
    provider_python = tmp_path / "python"
    provider_script = tmp_path / "run_moirai2_provider.py"
    provider_python.write_text("", encoding="utf-8")
    provider_script.write_text("", encoding="utf-8")
    return ForecastMcpConfig(
        server={
            "host": "127.0.0.1",
            "port": 18778,
            "artifact_root": tmp_path / "artifacts",
        },
        route={
            "repo_root": tmp_path,
            "provider_python": provider_python,
            "provider_script": provider_script,
            "approved_request": request_path,
            "request_manifest": manifest_path,
            "runtime_lane": "cuda13-experimental",
        },
        qwen=HttpRuntimeConfig(
            running_url="http://127.0.0.1:18081/running",
            running_contains="qwen",
            start_url="http://127.0.0.1:18081/start",
            stop_url="http://127.0.0.1:18081/stop",
        ),
        gpu=GpuProbeConfig(index=0),
        gate=ExternalGateConfig(
            status_url="http://127.0.0.1:18083/control/status",
            quiesce_url="http://127.0.0.1:18083/control/quiesce",
            close_url="http://127.0.0.1:18083/control/close",
            open_url="http://127.0.0.1:18083/control/open",
        ),
        lock_path=tmp_path / "gpu-exclusive.lock",
    )


class _FakeSupervisor:
    def __init__(self, config: Any) -> None:
        self.config = config

    def run(self) -> dict[str, Any]:
        command = self.config.forecast.command
        response_path = Path(command[command.index("--response") + 1])
        response = Moirai2ProviderResponse(
            status="OK",
            phase="predict",
            message="fake verified provider",
            model_identity={
                "model_id": MODEL_ID,
                "repo_id": REPO_ID,
                "revision": MODEL_REVISION,
            },
            point_forecast=[[1.25, 4.5, 8.75]],
            series_identity=["n1", "n2", "n3"],
            prediction_index=[1],
            runtime_evidence=RuntimeEvidence(
                process_id=4321,
                package_version="2.0.0",
                runtime_lane="cuda13-experimental",
                requested_device="cuda",
                execution_device="cuda",
                model_parameter_device="cuda:0",
                output_shape=[1, 3],
                all_quantiles_finite=True,
                quantile_monotonicity=True,
                cpu_fallback=False,
            ),
            gpu_evidence=GpuEvidence(
                requested_device="cuda",
                execution_device="cuda",
                cuda_available=True,
                provider_pid=4321,
                gpu_pid=4321,
                peak_vram_bytes=1024,
                cpu_fallback=False,
            ),
        )
        response_path.write_text(response.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return {
            "status": "PASS",
            "state": "IDLE",
            "qwen_initially_running": True,
            "qwen_stopped": True,
            "qwen_restored": True,
            "gate_reopened": True,
            "forecast_exit_code": 0,
            "failure": None,
        }


def test_llm_contract_rejects_shell_path_and_scope_override() -> None:
    with pytest.raises(ValidationError):
        ForecastToolRequest.model_validate(
            {
                "game": "numbers3",
                "model": "moirai2",
                "horizon": 1,
                "device": "cuda",
                "scope": "development",
                "command": "rm -rf /",
            }
        )
    with pytest.raises(ValidationError):
        ForecastToolRequest(scope="holdout")  # type: ignore[arg-type]


def test_forecast_runs_only_fixed_approved_route_and_seals_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []

    monkeypatch.setattr(
        ForecastMcpService,
        "_verify_approved_snapshot",
        staticmethod(lambda _: {"snapshot_path": "test-snapshot"}),
    )

    def factory(config: Any) -> _FakeSupervisor:
        captured.append(config)
        return _FakeSupervisor(config)

    service = ForecastMcpService(_config(tmp_path), supervisor_factory=factory)
    result = service.forecast(ForecastToolRequest())

    assert result["status"] == "PASS"
    assert result["route"] == {
        "game": "numbers3",
        "model": "moirai2",
        "horizon": 1,
        "device": "cuda",
        "scope": "development",
    }
    assert result["model_identity"]["repo_id"] == REPO_ID
    assert result["model_identity"]["revision"] == MODEL_REVISION
    assert result["prediction"]["point_forecast"] == [[1.25, 4.5, 8.75]]
    assert len(result["prediction_sha256"]) == 64
    assert result["route_provenance"]["runtime_lane"] == "cuda13-experimental"
    assert result["holdout_access"] is False
    assert result["prospective_access"] is False
    assert result["actual_access"] is False

    assert len(captured) == 1
    command = captured[0].forecast.command
    assert command[1].endswith("run_moirai2_provider.py")
    assert "--request" in command
    assert "--response" in command
    assert "--runtime-lane" in command
    assert "holdout" not in " ".join(command).lower()
    assert "prospective" not in " ".join(command).lower()
    assert captured[0].require_qwen_initially_running is True

    run_dir = tmp_path / "artifacts" / result["run_id"]
    assert (run_dir / "FORECAST_MCP_RESULT.json").is_file()
    assert (run_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (run_dir / "SHA256SUMS").is_file()


def test_manifest_hash_mismatch_fails_before_supervisor(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.route.approved_request.write_text("{}\n", encoding="utf-8")
    calls = 0

    def factory(_: Any) -> _FakeSupervisor:
        nonlocal calls
        calls += 1
        raise AssertionError("supervisor must not run")

    service = ForecastMcpService(config, supervisor_factory=factory)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        service.forecast(ForecastToolRequest())
    assert calls == 0


def test_machine_route_config_rejects_non_loopback_or_non_cuda_lane(tmp_path: Path) -> None:
    payload = _config(tmp_path).model_dump(mode="json")

    payload["server"]["host"] = "0.0.0.0"
    with pytest.raises(ValidationError):
        ForecastMcpConfig.model_validate(payload)

    payload = _config(tmp_path).model_dump(mode="json")
    payload["server"]["port"] = 18779
    with pytest.raises(ValidationError):
        ForecastMcpConfig.model_validate(payload)

    payload = _config(tmp_path).model_dump(mode="json")
    payload["route"]["runtime_lane"] = "cpu"
    with pytest.raises(ValidationError):
        ForecastMcpConfig.model_validate(payload)


def test_forecast_requires_qwen_to_have_been_unloaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SupervisorWithoutStop(_FakeSupervisor):
        def run(self) -> dict[str, Any]:
            result = super().run()
            result["qwen_stopped"] = False
            return result

    monkeypatch.setattr(
        ForecastMcpService,
        "_verify_approved_snapshot",
        staticmethod(lambda _: {"snapshot_path": "test-snapshot"}),
    )
    service = ForecastMcpService(
        _config(tmp_path),
        supervisor_factory=lambda config: SupervisorWithoutStop(config),
    )

    with pytest.raises(RuntimeError, match="not unloaded"):
        service.forecast(ForecastToolRequest())


def test_status_requires_live_qwen_open_gate_and_gpu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        def __init__(self, _: Any) -> None:
            pass

        def running(self) -> bool:
            return True

    class Gate:
        def __init__(self, _: Any) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {"state": "OPEN", "in_flight": 0}

    class Gpu:
        def __init__(self, _: Any) -> None:
            pass

        class Snapshot:
            index = 0
            memory_used_mib = 100
            memory_total_mib = 16303

        def snapshot(self) -> Snapshot:
            return self.Snapshot()

    monkeypatch.setattr("loto.forecast_mcp.service.HttpRuntime", Runtime)
    monkeypatch.setattr("loto.forecast_mcp.service.ExternalGate", Gate)
    monkeypatch.setattr("loto.forecast_mcp.service.NvidiaSmiProbe", Gpu)
    monkeypatch.setattr(
        ForecastMcpService,
        "_verify_approved_snapshot",
        staticmethod(lambda _: {"snapshot_path": "test-snapshot"}),
    )

    ready = ForecastMcpService(_config(tmp_path)).status()

    assert ready["status"] == "READY"
    assert ready["gate"] == {"state": "OPEN", "in_flight": 0}
    assert ready["readiness_errors"] == []
