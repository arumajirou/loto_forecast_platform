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


def _run_provider(lane: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(LANES[lane])
    return subprocess.run(
        [sys.executable, "-m", "loto_gluonts_provider", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_p5_fit_predict_blocks_without_lane_runtime(
    lane: str,
    tmp_path: Path,
) -> None:
    request_path = tmp_path / f"{lane}-fit-request.json"
    response_path = tmp_path / f"{lane}-fit-response.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": f"{lane}-fit",
                "run_id": "run-p5",
                "lane": lane,
                "operation": "fit_predict",
                "model_class": "DeepAREstimator",
                "prediction_length": 1,
                "context_length": 8,
                "seed": 1,
                "device": "cpu",
                "freq": "D",
                "dataset": [
                    {
                        "item_id": "series-1",
                        "start": "2000-01-01",
                        "target": [float(index) for index in range(32)],
                    }
                ],
                "artifact_dir": str(tmp_path / f"{lane}-predictor"),
                "arguments": {"p5_lifecycle_certification": True},
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
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(response_path.read_text("utf-8"))
    assert payload["status"] == "EXECUTION_PENDING"
    fit = payload["metadata"]["predictor_fit_serialize"]
    assert fit["outcome"] == "BLOCKED"
    assert fit["checks"]["version"] == "BLOCKED"
    assert payload["predictions"] == []


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_p5_load_predict_fails_closed_without_manifest(
    lane: str,
    tmp_path: Path,
) -> None:
    request_path = tmp_path / f"{lane}-load-request.json"
    response_path = tmp_path / f"{lane}-load-response.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": f"{lane}-load",
                "run_id": "run-p5",
                "lane": lane,
                "operation": "load_predict",
                "model_class": "DeepAREstimator",
                "prediction_length": 1,
                "context_length": 8,
                "seed": 1,
                "device": "cpu",
                "artifact_dir": str(tmp_path / "missing-predictor"),
                "arguments": {"p5_reload_certification": True},
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
    )

    assert completed.returncode == 1
    payload = json.loads(response_path.read_text("utf-8"))
    assert payload["status"] == "FAILED"
    assert payload["metadata"]["predictor_reload"]["outcome"] == "FAILED"
    assert payload["errors"]


def test_p5_contract_sources_are_identical() -> None:
    root_serialization = (
        ROOT / "src" / "loto" / "adapters" / "gluonts" / "serialization.py"
    ).read_bytes()
    compat_serialization = (
        LANES["compat"] / "loto_gluonts_provider" / "serialization.py"
    ).read_bytes()
    latest_serialization = (
        LANES["latest"] / "loto_gluonts_provider" / "serialization.py"
    ).read_bytes()
    assert root_serialization == compat_serialization == latest_serialization

    compat_runtime = (
        LANES["compat"] / "loto_gluonts_provider" / "serialization_runtime.py"
    ).read_bytes()
    latest_runtime = (
        LANES["latest"] / "loto_gluonts_provider" / "serialization_runtime.py"
    ).read_bytes()
    assert compat_runtime == latest_runtime

    compat_cli = (LANES["compat"] / "loto_gluonts_provider" / "cli.py").read_bytes()
    latest_cli = (LANES["latest"] / "loto_gluonts_provider" / "cli.py").read_bytes()
    assert compat_cli == latest_cli
