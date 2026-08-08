from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.timer_s1_campaign.model_manifest import TimerS1ModelManifest, load_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_is_fail_closed_until_all_hashes_are_known() -> None:
    manifest = load_manifest(ROOT / "configs/timer_s1_campaign/model_manifest.json")
    assert manifest.observed_model_revision == "8911430cc7f32add5c8913afe12e3b05742f5bb2"
    assert manifest.observed_source_revision == "0d35f1fe891243453ca1bfa903b5271cf9eb85cb"
    assert manifest.model_revision == "UNPINNED"
    assert manifest.source_revision == "UNPINNED"
    assert manifest.formal_pin_complete is False
    assert manifest.mirror_fallback_enabled is False


def test_manifest_covers_expected_remote_code_and_four_weight_shards() -> None:
    manifest = load_manifest(ROOT / "configs/timer_s1_campaign/model_manifest.json")
    paths = {artifact.path for artifact in manifest.artifacts}
    assert {
        "configuration_TimerS1.py",
        "modeling_TimerS1.py",
        "ts_generation_mixin.py",
    }.issubset(paths)
    assert {f"model-{index:05d}-of-00004.safetensors" for index in range(1, 5)}.issubset(paths)


def test_manifest_rejects_unsafe_artifact_path() -> None:
    import pytest
    from pydantic import ValidationError

    from loto.timer_s1_campaign.model_manifest import ArtifactRecord

    with pytest.raises(ValidationError, match="snapshot root"):
        ArtifactRecord(
            path="../escape.bin",
            size_bytes=1,
            sha256="a" * 64,
            required=True,
            kind="weight",
        )


def manifest_payload() -> dict[str, object]:
    return json.loads(
        (ROOT / "configs/timer_s1_campaign/model_manifest.json").read_text(encoding="utf-8")
    )


def test_manifest_rejects_missing_required_core_artifact() -> None:
    payload = manifest_payload()
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    payload["artifacts"] = [item for item in artifacts if item["path"] != "modeling_TimerS1.py"]
    with pytest.raises(ValidationError, match="missing required artifacts"):
        TimerS1ModelManifest.model_validate_json(json.dumps(payload))


def test_manifest_rejects_optional_or_misclassified_core_artifact() -> None:
    payload = manifest_payload()
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    config = next(item for item in artifacts if item["path"] == "config.json")
    config["required"] = False
    with pytest.raises(ValidationError, match="marked optional"):
        TimerS1ModelManifest.model_validate_json(json.dumps(payload))
