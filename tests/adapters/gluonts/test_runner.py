from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.adapters.gluonts.inventory import (
    CheckState,
    FormalAvailability,
    InventoryCategory,
    RuntimeInventory,
    RuntimeInventoryEntry,
    inventory_sha256,
)
from loto.adapters.gluonts.protocol import (
    EnvironmentLane,
    GluonTSProviderRequest,
    ProviderOperation,
    ProviderStatus,
    protocol_schema_sha256,
)
from loto.adapters.gluonts.runner import invoke_provider, sha256_file


def _request() -> GluonTSProviderRequest:
    return GluonTSProviderRequest(
        request_id="request-1",
        run_id="run-1",
        lane=EnvironmentLane.COMPAT,
        operation=ProviderOperation.MODEL_DISCOVERY,
        model_class="*",
    )


def _inventory() -> RuntimeInventory:
    return RuntimeInventory(
        lane="compat",
        generated_at_utc="2026-08-05T00:00:00+00:00",
        entries=[
            RuntimeInventoryEntry(
                name="DeepAREstimator",
                category=InventoryCategory.PYTORCH_ESTIMATOR,
                module="gluonts.torch.model.deepar",
                import_state=CheckState.PASS,
                export_state=CheckState.PASS,
                class_state=CheckState.PASS,
                signature_state=CheckState.PASS,
                formal_availability=FormalAvailability.DISCOVERED_ONLY,
            )
        ],
    )


def test_invoke_provider_persists_validated_artifacts(tmp_path: Path) -> None:
    inventory = _inventory()
    script = tmp_path / "provider.py"
    script.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', type=Path, required=True)
parser.add_argument('--response', type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.request.read_text('utf-8'))
args.response.write_text(json.dumps({
    'schema_version': 1,
    'request_id': request['request_id'],
    'run_id': request['run_id'],
    'lane': request['lane'],
    'status': 'PARTIALLY_VERIFIED',
    'predictions': [],
    'metadata': {
        'source': 'fake-provider',
        'provider_identity': {'protocol_schema_sha256': '__SCHEMA_HASH__'},
        'runtime_inventory': __INVENTORY__,
        'runtime_inventory_sha256': '__INVENTORY_HASH__',
    },
    'errors': [],
}, sort_keys=True), encoding='utf-8')
print('provider stdout')
""".strip()
        .replace("__SCHEMA_HASH__", protocol_schema_sha256())
        .replace("__INVENTORY__", repr(inventory.model_dump(mode="json")))
        .replace("__INVENTORY_HASH__", inventory_sha256(inventory)),
        encoding="utf-8",
    )

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.return_code == 0
    assert invocation.response.status is ProviderStatus.PARTIALLY_VERIFIED
    assert invocation.request_path.exists()
    assert invocation.response_path.exists()
    assert invocation.stdout_path.read_text("utf-8").strip() == "provider stdout"
    assert invocation.request_sha256 == sha256_file(invocation.request_path)
    assert invocation.response_sha256 == sha256_file(invocation.response_path)
    assert invocation.inventory_path is not None
    assert invocation.inventory_path.exists()
    assert invocation.inventory_sha256 == sha256_file(invocation.inventory_path)
    assert invocation.manifest_path is not None
    assert invocation.manifest_path.exists()
    assert invocation.manifest_sha256 == sha256_file(invocation.manifest_path)


def test_invoke_provider_fails_closed_when_response_is_missing(tmp_path: Path) -> None:
    script = tmp_path / "silent_provider.py"
    script.write_text("print('no response')\n", encoding="utf-8")

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.response.status is ProviderStatus.FAILED
    assert "without response.json" in invocation.response.errors[0]
    payload = json.loads(invocation.response_path.read_text("utf-8"))
    assert payload["status"] == "FAILED"


def test_invoke_provider_rejects_inventory_hash_mismatch(tmp_path: Path) -> None:
    inventory = _inventory()
    script = tmp_path / "bad_inventory_provider.py"
    script.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', type=Path, required=True)
parser.add_argument('--response', type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.request.read_text('utf-8'))
args.response.write_text(json.dumps({
    'schema_version': 1,
    'request_id': request['request_id'],
    'run_id': request['run_id'],
    'lane': request['lane'],
    'status': 'PARTIALLY_VERIFIED',
    'predictions': [],
    'metadata': {
        'provider_identity': {'protocol_schema_sha256': '__SCHEMA_HASH__'},
        'runtime_inventory': __INVENTORY__,
        'runtime_inventory_sha256': '0' * 64,
    },
    'errors': [],
}, sort_keys=True), encoding='utf-8')
""".strip()
        .replace("__SCHEMA_HASH__", protocol_schema_sha256())
        .replace("__INVENTORY__", repr(inventory.model_dump(mode="json"))),
        encoding="utf-8",
    )

    invocation = invoke_provider(
        _request(),
        [sys.executable, str(script)],
        tmp_path / "artifacts",
        timeout_seconds=10,
    )

    assert invocation.response.status is ProviderStatus.FAILED
    assert "inventory SHA-256 mismatch" in invocation.response.errors[0]
    assert invocation.inventory_path is None
