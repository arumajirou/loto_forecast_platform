from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from loto.moirai2_campaign.runtime_evidence_gate import verify_campaign_manifest


ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = ROOT / "scripts" / "run_moirai2_runtime_campaign_p8c.py"
    spec = importlib.util.spec_from_file_location("p8c_campaign_wrapper", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seal_output_injects_source_and_rebuilds_manifest(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "campaign"
    output.mkdir()
    (output / "payload.txt").write_text("payload\n", encoding="utf-8")
    (output / "campaign_config.json").write_text(
        json.dumps({"campaign_id": "run"}) + "\n",
        encoding="utf-8",
    )
    (output / "ARTIFACT_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("old\n", encoding="utf-8")
    source = {
        "schema_version": "moirai2-source-identity-v1",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "worktree_clean": True,
        "changed_paths": [],
        "principal_file_sha256": {"source.py": "c" * 64},
    }
    module._seal_output(
        output_dir=output,
        source_identity=source,
        command=["python", "runner.py"],
        return_code=0,
        started_ns=1,
        ended_ns=2,
        stdout="ok\n",
        stderr="",
    )
    config = json.loads((output / "campaign_config.json").read_text(encoding="utf-8"))
    assert config["source_identity"] == source
    assert config["formal_entrypoint"].endswith("run_moirai2_runtime_campaign_p8c.py")
    launch = json.loads(
        (output / "P8C_LAUNCH_EVIDENCE.json").read_text(encoding="utf-8")
    )
    assert launch["return_code"] == 0
    assert launch["source_identity"] == source
    verification = verify_campaign_manifest(output)
    assert verification.verified_file_count > 0


def test_command_preserves_formal_campaign_arguments(tmp_path: Path) -> None:
    module = _module()
    arguments = argparse.Namespace(
        campaign_id="run-id",
        snapshot_path=tmp_path / "snapshot",
        runtime_lane="supported-py311",
        device="cpu",
        output_dir=tmp_path / "output",
        history_length=128,
        context_length=128,
        prediction_length=1,
        timeout_seconds=1800,
        monitor_interval_seconds=0.25,
        case=["draw-target-only"],
        prepare_only=False,
    )
    command = module._command(arguments)
    assert "--campaign-id" in command
    assert "run-id" in command
    assert "--runtime-lane" in command
    assert "supported-py311" in command
    assert command[-2:] == ["--case", "draw-target-only"]


def test_artifact_manifest_excludes_self_and_sha(tmp_path: Path) -> None:
    module = _module()
    (tmp_path / "one.txt").write_text("1\n", encoding="utf-8")
    (tmp_path / "ARTIFACT_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("x\n", encoding="utf-8")
    manifest = module._artifact_manifest(tmp_path)
    assert manifest["files"] == ["one.txt"]
    assert manifest["file_count"] == 1
