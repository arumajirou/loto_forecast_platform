from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.adapters.tabpfn_ts.runtime_certifier import (
    GPUProcessSample,
    ProviderRunEvidence,
    RuntimeCertificationConfig,
    RuntimeCertificationError,
    build_formal_provider_request,
    canonical_prediction_sha256,
    compare_process_replays,
    parse_nvidia_compute_apps,
    validate_provider_response,
)
from loto.adapters.tabpfn_ts.manifests import V2_WEIGHT_SHA256


def _gpu_response(*, pid: int = 123, cpu_fallback: bool = False) -> dict[str, object]:
    return {
        "status": "OK",
        "schema_version": 1,
        "predictions": [float(index) / 10 for index in range(37)],
        "prediction_shape": [37],
        "finite": True,
        "properties": {
            "weight_sha256": V2_WEIGHT_SHA256,
            "seed": 1,
        },
        "gpu_evidence": {
            "requested_device": "cuda",
            "execution_device": "cpu" if cpu_fallback else "cuda",
            "cpu_fallback": cpu_fallback,
            "gpu_pid": pid,
            "peak_vram_bytes": 1024,
            "model_parameter_devices": ["cuda:0"],
        },
    }


def _run(pid: int, predictions: list[float]) -> ProviderRunEvidence:
    return ProviderRunEvidence(
        run_index=pid,
        process_pid=pid,
        exit_code=0,
        started_at_utc="2026-08-06T00:00:00+00:00",
        finished_at_utc="2026-08-06T00:00:01+00:00",
        request_path=f"request-{pid}.json",
        response_path=f"response-{pid}.json",
        stdout_path=f"stdout-{pid}.log",
        stderr_path=f"stderr-{pid}.log",
        response_sha256="a" * 64,
        prediction_sha256=canonical_prediction_sha256(predictions),
        predictions=predictions,
        prediction_shape=[37],
        requested_device="cuda",
        execution_device="cuda",
        cpu_fallback=False,
        provider_gpu_pid=pid,
        provider_peak_vram_bytes=1024,
        parameter_devices=["cuda:0"],
        external_gpu_samples=[
            GPUProcessSample(
                pid=pid,
                gpu_uuid="GPU-test",
                used_memory_bytes=1024,
                observed_at_utc="2026-08-06T00:00:00+00:00",
            )
        ],
        pid_released_after_exit=True,
    )


def test_parse_nvidia_compute_apps_converts_mib_to_bytes() -> None:
    rows = parse_nvidia_compute_apps(
        "123, GPU-abc, 17\n",
        observed_at_utc="2026-08-06T00:00:00+00:00",
    )
    assert rows[0].pid == 123
    assert rows[0].gpu_uuid == "GPU-abc"
    assert rows[0].used_memory_bytes == 17 * 1024 * 1024


def test_parse_nvidia_compute_apps_rejects_unknown_shape() -> None:
    with pytest.raises(RuntimeCertificationError, match="unexpected nvidia-smi"):
        parse_nvidia_compute_apps("123, GPU-only-two-fields")


def test_formal_request_pins_identity_offline_seed_and_license(tmp_path: Path) -> None:
    payload = build_formal_provider_request(
        {
            "history": [{"draw_date": "2026-01-01", **{f"n{i}": i for i in range(1, 8)}}],
            "prediction_length": 1,
            "repo_id": "untrusted",
        },
        snapshot_path=tmp_path / "snapshot",
        device="cuda",
        seed=7,
    )
    assert payload["repo_id"] == "Prior-Labs/TabPFN-v2-reg"
    assert payload["seed"] == 7
    assert payload["license_accepted"] is True
    assert payload["network_access"] is False
    assert payload["telemetry_disabled"] is True


def test_formal_request_rejects_multi_step_legacy_runtime(tmp_path: Path) -> None:
    with pytest.raises(RuntimeCertificationError, match="prediction_length=1"):
        build_formal_provider_request(
            {"history": [{}], "prediction_length": 2},
            snapshot_path=tmp_path,
            device="cuda",
            seed=1,
        )


def test_validate_provider_response_accepts_formal_cuda_evidence() -> None:
    sample = GPUProcessSample(
        pid=123,
        gpu_uuid="GPU-test",
        used_memory_bytes=1024,
        observed_at_utc="2026-08-06T00:00:00+00:00",
    )
    predictions, gpu = validate_provider_response(
        _gpu_response(),
        expected_device="cuda",
        process_pid=123,
        external_samples=[sample],
        expected_seed=1,
    )
    assert len(predictions) == 37
    assert gpu["execution_device"] == "cuda"


def test_validate_provider_response_rejects_cpu_fallback() -> None:
    with pytest.raises(RuntimeCertificationError, match="CPU fallback"):
        validate_provider_response(
            _gpu_response(cpu_fallback=True),
            expected_device="cuda",
            process_pid=123,
            external_samples=[],
            expected_seed=1,
        )


def test_validate_provider_response_rejects_missing_external_pid() -> None:
    with pytest.raises(RuntimeCertificationError, match="did not observe provider PID"):
        validate_provider_response(
            _gpu_response(),
            expected_device="cuda",
            process_pid=123,
            external_samples=[],
            expected_seed=1,
        )


def test_validate_provider_response_rejects_wrong_weight_hash() -> None:
    response = _gpu_response()
    properties = response["properties"]
    assert isinstance(properties, dict)
    properties["weight_sha256"] = "0" * 64
    sample = GPUProcessSample(
        pid=123,
        gpu_uuid="GPU-test",
        used_memory_bytes=1024,
        observed_at_utc="2026-08-06T00:00:00+00:00",
    )
    with pytest.raises(RuntimeCertificationError, match="weight SHA-256"):
        validate_provider_response(
            response,
            expected_device="cuda",
            process_pid=123,
            external_samples=[sample],
            expected_seed=1,
        )


def test_compare_process_replays_requires_distinct_processes() -> None:
    predictions = [float(index) for index in range(37)]
    first = _run(1, predictions)
    second = first.model_copy(update={"run_index": 2})
    with pytest.raises(RuntimeCertificationError, match="distinct provider processes"):
        compare_process_replays([first, second], absolute_tolerance=0.0)


def test_compare_process_replays_reports_maximum_difference() -> None:
    first_values = [float(index) for index in range(37)]
    second_values = list(first_values)
    second_values[-1] += 0.01
    deterministic, maximum = compare_process_replays(
        [_run(1, first_values), _run(2, second_values)],
        absolute_tolerance=0.02,
    )
    assert deterministic is True
    assert maximum == pytest.approx(0.01)


def test_runtime_config_requires_at_least_two_repeats(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RuntimeCertificationConfig(
            run_id="test",
            repo_root=tmp_path,
            provider_python=tmp_path / "python",
            provider_script=tmp_path / "provider.py",
            request_path=tmp_path / "request.json",
            snapshot_path=tmp_path / "snapshot",
            repository_cache_root=tmp_path / "cache",
            output_root=tmp_path / "artifacts",
            repeats=1,
        )


def test_prediction_lock_hash_is_stable() -> None:
    values = [float(index) for index in range(37)]
    assert canonical_prediction_sha256(values) == canonical_prediction_sha256(values)
    assert len(canonical_prediction_sha256(values)) == 64


def test_failure_payload_remains_json_serializable() -> None:
    payload = {"status": "FAIL", "failure_reason": "checkpoint unavailable"}
    assert json.loads(json.dumps(payload))["status"] == "FAIL"


def test_provider_process_orchestration_cpu_smoke(tmp_path: Path) -> None:
    import sys

    from loto.adapters.tabpfn_ts.runtime_process import run_provider_process

    fake_provider = tmp_path / "fake_provider.py"
    fake_provider.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', type=Path, required=True)
parser.add_argument('--response', type=Path, required=True)
parser.add_argument('--certification-hold-seconds')
args = parser.parse_args()
request = json.loads(args.request.read_text(encoding='utf-8'))
response = {
    'status': 'OK',
    'schema_version': 1,
    'predictions': [index / 10 for index in range(37)],
    'prediction_shape': [37],
    'finite': True,
    'properties': {
        'weight_sha256': '2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736',
        'seed': request['seed'],
    },
    'gpu_evidence': {
        'requested_device': 'cpu',
        'execution_device': 'cpu',
        'cpu_fallback': False,
        'gpu_pid': None,
        'peak_vram_bytes': 0,
        'model_parameter_devices': ['cpu'],
    },
}
args.response.write_text(json.dumps(response), encoding='utf-8')
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = RuntimeCertificationConfig(
        run_id="cpu-smoke",
        repo_root=tmp_path,
        provider_python=Path(sys.executable),
        provider_script=fake_provider,
        request_path=tmp_path / "source-request.json",
        snapshot_path=tmp_path / "snapshot",
        repository_cache_root=tmp_path / "cache",
        output_root=tmp_path / "artifacts",
        device="cpu",
        repeats=2,
        hold_seconds=0.5,
    )
    evidence = run_provider_process(
        config,
        run_index=1,
        formal_request={"seed": 1},
        gpu_probe=lambda _command: [],
    )
    assert evidence.exit_code == 0
    assert evidence.execution_device == "cpu"
    assert evidence.provider_gpu_pid is None
    assert evidence.pid_released_after_exit is True


def test_certify_runtime_blocks_before_process_when_checkpoint_is_missing(tmp_path: Path) -> None:
    import sys

    from loto.adapters.tabpfn_ts.runtime_certifier import certify_runtime
    from loto.adapters.tabpfn_ts.manifests import V2_REVISION

    provider_script = tmp_path / "provider.py"
    provider_script.write_text("raise SystemExit('must not run')\n", encoding="utf-8")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "history": [
                    {
                        "draw_date": "2026-01-01",
                        **{f"n{index}": index for index in range(1, 8)},
                    }
                ],
                "prediction_length": 1,
            }
        ),
        encoding="utf-8",
    )
    cache_root = tmp_path / "models--Prior-Labs--TabPFN-v2-reg"
    snapshot = cache_root / "snapshots" / V2_REVISION
    snapshot.mkdir(parents=True)
    config = RuntimeCertificationConfig(
        run_id="missing-checkpoint",
        repo_root=tmp_path,
        provider_python=Path(sys.executable),
        provider_script=provider_script,
        request_path=request_path,
        snapshot_path=snapshot,
        repository_cache_root=cache_root,
        output_root=tmp_path / "artifacts",
        device="cpu",
    )
    with pytest.raises(Exception, match="checkpoint does not exist"):
        certify_runtime(config, gpu_probe=lambda _command: [])
    assert not (config.output_root / config.run_id).exists()
