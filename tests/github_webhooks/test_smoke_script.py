from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "github_webhooks" / "smoke_receiver.py"
POLICY = ROOT / "configs" / "github_webhooks" / "receiver_v1.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("github_webhook_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_excludes_itself_and_hashes_report(tmp_path: Path) -> None:
    module = _load_module()
    output = tmp_path / "evidence"
    output.mkdir()
    module.write_json(output / "SMOKE_REPORT.json", {"status": "PASS"})
    manifest = module.build_manifest(output)
    assert manifest["files"] == [
        {
            "path": "SMOKE_REPORT.json",
            "size_bytes": (output / "SMOKE_REPORT.json").stat().st_size,
            "sha256": hashlib.sha256((output / "SMOKE_REPORT.json").read_bytes()).hexdigest(),
        }
    ]


def test_smoke_script_main_creates_secret_free_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    output = tmp_path / "smoke-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--policy",
            str(POLICY),
            "--output",
            str(output),
        ],
    )
    assert module.main() == 0
    report = json.loads((output / "SMOKE_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["first"]["status_code"] == 202
    assert report["duplicate"]["status_code"] == 200
    assert report["delivery_count"] == 1
    assert report["outbox_count"] == 1
    assert report["secret_persisted"] is False
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.iterdir()
        if path.is_file()
    )
    assert "sha256=" not in combined
    assert module.FIXTURE_SECRET.hex() not in combined
