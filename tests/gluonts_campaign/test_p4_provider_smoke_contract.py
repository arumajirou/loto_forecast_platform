from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANES = {
    "compat": ROOT / "environments" / "gluonts-compat" / "src",
    "latest": ROOT / "environments" / "gluonts-latest" / "src",
}


def _run_provider(
    lane: str,
    *arguments: str,
    extra_environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(LANES[lane])
    environment.update(extra_environment or {})
    return subprocess.run(
        [sys.executable, "-m", "loto_gluonts_provider", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_runtime_certify_persists_blocked_deepar_smoke_without_false_success(
    lane: str,
    tmp_path: Path,
) -> None:
    request_path = tmp_path / f"{lane}-request.json"
    response_path = tmp_path / f"{lane}-response.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": f"request-p4-{lane}",
                "run_id": "run-p4",
                "lane": lane,
                "operation": "runtime_certify",
                "model_class": "DeepAREstimator",
                "prediction_length": 1,
                "context_length": 8,
                "seed": 1,
                "device": "cpu",
                "arguments": {"run_deepar_cpu_smoke": True},
            }
        ),
        encoding="utf-8",
    )

    completed = _run_provider(
        lane,
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        extra_environment={"LOTO_GLUONTS_SKIP_DEEPAR_SMOKE": "1"},
    )

    assert completed.returncode == 0, completed.stderr
    response = json.loads(response_path.read_text("utf-8"))
    assert response["status"] == "EXECUTION_PENDING"
    metadata = response["metadata"]
    smoke = metadata["deep_ar_cpu_smoke"]
    assert smoke["outcome"] == "BLOCKED"
    assert smoke["checks"]["version"] == "BLOCKED"
    assert metadata["fit_predict_certified"] is False
    assert metadata["device_certified"] is False
    assert metadata["formal_runtime_verified"] == 0
    assert len(metadata["deep_ar_cpu_smoke_sha256"]) == 64


def test_deepar_cpu_smoke_rejects_cuda_request(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "request-cuda",
                "run_id": "run-p4",
                "lane": "compat",
                "operation": "runtime_certify",
                "model_class": "DeepAREstimator",
                "device": "cuda",
                "arguments": {"run_deepar_cpu_smoke": True},
            }
        ),
        encoding="utf-8",
    )

    completed = _run_provider(
        "compat",
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    )

    assert completed.returncode == 1
    response = json.loads(response_path.read_text("utf-8"))
    assert response["status"] == "FAILED"
    assert "requires device auto or cpu" in response["errors"][0]
