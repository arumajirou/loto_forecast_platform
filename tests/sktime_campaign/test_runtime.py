from __future__ import annotations

import hashlib
import json
from pathlib import Path

from loto.sktime_campaign import runtime
from loto.sktime_campaign.protocol import ProviderRequest, ProviderStatus


def _fake_inventory_rows() -> list[dict[str, object]]:
    return [
        {
            "name": "NaiveForecaster",
            "class_path": "sktime.forecasting.naive.NaiveForecaster",
            "constructor_signature": "(strategy='last', sp=1, window_length=None)",
            "package_version": "1.0.1",
            "dependency_state": "CORE_COMPATIBLE",
            "import_status": "IMPORTABLE",
            "construct_status": "NOT_ATTEMPTED",
            "fit_status": "NOT_ATTEMPTED",
            "predict_status": "NOT_ATTEMPTED",
            "save_load_status": "NOT_ATTEMPTED",
            "tags": {"property:randomness": "deterministic"},
        }
    ]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inventory_operation_writes_manifest_and_portable_hashes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime, "installed_sktime_version", lambda: "1.0.1")
    monkeypatch.setattr(runtime, "discover_forecasters", _fake_inventory_rows)
    output_dir = tmp_path / "inventory"
    request = ProviderRequest(
        operation="inventory",
        output_dir=str(output_dir),
    )

    response = runtime.execute_request(request)

    assert response.status is ProviderStatus.PASS
    assert response.inventory is not None
    assert response.inventory["discovered"] == 1
    required = {
        "FORECASTER_INVENTORY.json",
        "FORECASTER_INVENTORY.csv",
        "INVENTORY_SUMMARY.json",
        "response.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }
    assert required <= {path.name for path in output_dir.iterdir()}

    manifest = json.loads((output_dir / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["operation"] == "inventory"

    for line in (output_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative_path = line.split("  ", maxsplit=1)
        assert _digest(output_dir / relative_path) == expected


def test_version_mismatch_fails_closed_and_keeps_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "installed_sktime_version", lambda: "0.40.1")
    output_dir = tmp_path / "version-mismatch"
    request = ProviderRequest(
        operation="inventory",
        output_dir=str(output_dir),
    )

    response = runtime.execute_request(request)

    assert response.status is ProviderStatus.FAILED
    assert response.error is not None
    assert "version mismatch" in response.error["message"]
    persisted = json.loads((output_dir / "response.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "FAILED"
    assert (output_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (output_dir / "SHA256SUMS").is_file()
