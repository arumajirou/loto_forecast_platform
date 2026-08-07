from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.adapters.gluonts.protocol import (
    EnvironmentLane,
    GluonTSProviderRequest,
    ProviderOperation,
    ProviderStatus,
    protocol_schema_sha256,
)
from loto.adapters.gluonts.runner import invoke_provider, sha256_file
from loto.adapters.gluonts.smoke import (
    DeepARCPUSmokeResult,
    run_deepar_cpu_smoke,
    smoke_sha256,
)


def _request() -> GluonTSProviderRequest:
    return GluonTSProviderRequest(
        request_id="request-p4",
        run_id="run-p4",
        lane=EnvironmentLane.COMPAT,
        operation=ProviderOperation.RUNTIME_CERTIFY,
        model_class="DeepAREstimator",
        device="cpu",
        arguments={"run_deepar_cpu_smoke": True},
    )


def _provider_script(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    path.write_text(
        f"""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', type=Path, required=True)
parser.add_argument('--response', type=Path, required=True)
args = parser.parse_args()
args.response.write_text({encoded!r}, encoding='utf-8')
""".strip(),
        encoding="utf-8",
    )


def _response_payload(smoke: DeepARCPUSmokeResult, smoke_sha: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "request-p4",
        "run_id": "run-p4",
        "lane": "compat",
        "status": "EXECUTION_PENDING",
        "predictions": [],
        "metadata": {
            "provider_identity": {"protocol_schema_sha256": protocol_schema_sha256()},
            "deep_ar_cpu_smoke": smoke.model_dump(mode="json"),
            "deep_ar_cpu_smoke_sha256": smoke_sha,
        },
        "errors": [],
    }


def test_runner_persists_validated_deepar_cpu_smoke(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE", "1")
    smoke = run_deepar_cpu_smoke("compat")
    script = tmp_path / "provider.py"
    _provider_script(script, _response_payload(smoke, smoke_sha256(smoke)))

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.response.status is ProviderStatus.EXECUTION_PENDING
    assert invocation.smoke_path is not None
    assert invocation.smoke_path.exists()
    assert invocation.smoke_sha256 == sha256_file(invocation.smoke_path)
    manifest = json.loads(invocation.manifest_path.read_text("utf-8"))
    assert manifest["deep_ar_cpu_smoke_sha256"] == invocation.smoke_sha256


def test_runner_fails_closed_on_smoke_hash_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE", "1")
    smoke = run_deepar_cpu_smoke("compat")
    script = tmp_path / "provider.py"
    _provider_script(script, _response_payload(smoke, "0" * 64))

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.response.status is ProviderStatus.FAILED
    assert "smoke SHA-256 mismatch" in invocation.response.errors[0]
    assert invocation.smoke_path is None


def test_runner_persists_failed_smoke_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE", "1")
    smoke = run_deepar_cpu_smoke("compat")
    payload = _response_payload(smoke, smoke_sha256(smoke))
    payload["status"] = "FAILED"
    payload["errors"] = ["runtime smoke failed"]
    script = tmp_path / "provider.py"
    _provider_script(script, payload)

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.response.status is ProviderStatus.FAILED
    assert invocation.smoke_path is not None
    assert invocation.smoke_path.exists()
    assert invocation.smoke_sha256 == sha256_file(invocation.smoke_path)
