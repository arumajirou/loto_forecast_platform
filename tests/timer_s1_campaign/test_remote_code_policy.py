from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from loto.timer_s1_campaign.model_manifest import (
    ArtifactRecord,
    TimerS1ModelManifest,
)
from loto.timer_s1_campaign.remote_code_policy import (
    RemoteCodeReview,
    validate_snapshot,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(files: dict[str, bytes]) -> TimerS1ModelManifest:
    return TimerS1ModelManifest(
        schema_version=1,
        model_id="timer-s1",
        canonical_repo="bytedance-research/Timer-S1",
        mirror_repo="thuml/Timer-S1",
        arxiv_id="2603.04791",
        license="Apache-2.0",
        gated=False,
        trust_remote_code=True,
        model_revision="a" * 40,
        source_revision="b" * 40,
        observed_model_revision="a" * 40,
        observed_source_revision="b" * 40,
        mirror_revision="UNPINNED",
        package_versions={},
        python_compatibility="TEST",
        artifacts=tuple(
            ArtifactRecord(
                path=name,
                size_bytes=len(content),
                sha256=digest(content),
                required=True,
                kind="remote-code",
            )
            for name, content in files.items()
        ),
        mirror_fallback_enabled=False,
    )


def build_review(files: dict[str, bytes]) -> RemoteCodeReview:
    return RemoteCodeReview(
        schema_version=1,
        status="APPROVED",
        source_revision="b" * 40,
        reviewed_files={name: digest(content) for name, content in files.items()},
        shell_execution=False,
        subprocess_execution=False,
        dynamic_download=False,
        arbitrary_file_write=False,
        unapproved_external_imports=False,
        reviewer="test-reviewer",
        reviewed_at="2026-08-06T00:00:00Z",
    )


def write_snapshot(root: Path) -> dict[str, bytes]:
    files = {
        "configuration_TimerS1.py": b"# config\n",
        "modeling_TimerS1.py": b"# model\n",
        "ts_generation_mixin.py": b"# generation\n",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    return files


def set_offline_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(key, "1")


def test_reviewed_snapshot_passes_without_importing_remote_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = write_snapshot(tmp_path)
    set_offline_environment(monkeypatch)
    validate_snapshot(tmp_path, build_manifest(files), build_review(files))


def test_unknown_remote_python_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = write_snapshot(tmp_path)
    (tmp_path / "unknown.py").write_text("pass\n", encoding="utf-8")
    set_offline_environment(monkeypatch)
    with pytest.raises(ValueError, match="allowlist"):
        validate_snapshot(tmp_path, build_manifest(files), build_review(files))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_snapshot_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = write_snapshot(tmp_path)
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)
    set_offline_environment(monkeypatch)
    with pytest.raises(ValueError, match="symlink"):
        validate_snapshot(tmp_path, build_manifest(files), build_review(files))
