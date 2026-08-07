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


def _write_request(path: Path, lane: str, operation: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": f"request-{lane}-{operation}",
                "run_id": "run-p3",
                "lane": lane,
                "operation": operation,
                "model_class": "*",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_provider_identity_does_not_require_gluonts_import(lane: str) -> None:
    completed = _run_provider(lane, "--identity")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["lane"] == lane
    assert payload["protocol_schema_sha256"]
    assert "runtime_versions" in payload


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_model_discovery_writes_atomic_fail_closed_response(
    lane: str,
    tmp_path: Path,
) -> None:
    request_path = tmp_path / f"{lane}-request.json"
    response_path = tmp_path / f"{lane}-response.json"
    _write_request(request_path, lane, "model_discovery")

    completed = _run_provider(
        lane,
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(response_path.read_text("utf-8"))
    assert payload["status"] in {"PARTIALLY_VERIFIED", "EXECUTION_PENDING"}
    entries = payload["metadata"]["model_discovery"]["entries"]
    assert len(entries) == 9
    assert all("available" in entry for entry in entries)
    inventory = payload["metadata"]["runtime_inventory"]
    assert inventory["lane"] == lane
    assert inventory["summary"]["by_category"]["PYTORCH_ESTIMATOR"] == 9
    assert inventory["summary"]["formally_verified"] == 0
    assert len(payload["metadata"]["runtime_inventory_sha256"]) == 64


@pytest.mark.parametrize("lane", ["compat", "latest"])
def test_runtime_certify_inventory_separates_categories(lane: str, tmp_path: Path) -> None:
    request_path = tmp_path / f"{lane}-certify-request.json"
    response_path = tmp_path / f"{lane}-certify-response.json"
    _write_request(request_path, lane, "runtime_certify")

    completed = _run_provider(
        lane,
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(response_path.read_text("utf-8"))
    inventory = payload["metadata"]["runtime_inventory"]
    categories = inventory["summary"]["by_category"]
    assert categories["PYTORCH_ESTIMATOR"] == 9
    assert categories["DISTRIBUTION_OUTPUT"] == 15
    assert categories["NATIVE_PREDICTOR"] >= 1
    assert categories["EXTENSION"] >= 1
    assert inventory["summary"]["formally_verified"] == 0
    assert payload["metadata"]["fit_predict_certified"] is False
    assert payload["metadata"]["device_certified"] is False


def test_provider_rejects_lane_mismatch(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    _write_request(request_path, "latest", "runtime_certify")

    completed = _run_provider(
        "compat",
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    )

    assert completed.returncode == 1
    payload = json.loads(response_path.read_text("utf-8"))
    assert payload["status"] == "FAILED"
    assert "does not match provider lane" in payload["errors"][0]
