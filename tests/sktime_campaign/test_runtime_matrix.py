from __future__ import annotations

import json
from pathlib import Path

from loto.sktime_campaign import runtime
from loto.sktime_campaign.protocol import ProviderOperation, ProviderRequest


def test_execute_matrix_persists_partial_without_promoting_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime, "installed_sktime_version", lambda: "1.0.1")
    monkeypatch.setattr(
        runtime,
        "run_smoke_matrix",
        lambda request, output_dir: {
            "status": "PARTIAL",
            "summary": {
                "status": "PARTIAL",
                "total": 2,
                "counts": {
                    "PASS": 1,
                    "PARTIAL": 0,
                    "FAILED": 0,
                    "UNAVAILABLE": 1,
                },
                "all_requested_models_passed": False,
            },
            "results": [],
        },
    )
    request = ProviderRequest(
        operation=ProviderOperation.SMOKE_MATRIX,
        output_dir=str(tmp_path),
        environment_lane="classic-py312",
    )

    response = runtime.execute_request(request)

    assert response.status.value == "PARTIAL"
    persisted = json.loads((tmp_path / "response.json").read_text())
    manifest = json.loads((tmp_path / "ARTIFACT_MANIFEST.json").read_text())
    assert persisted["status"] == "PARTIAL"
    assert manifest["status"] == "PARTIAL"
    assert (tmp_path / "SHA256SUMS").is_file()
