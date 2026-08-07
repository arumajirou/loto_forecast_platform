from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from loto.mlforecast.handoff import (
    REQUIRED_DOCUMENTS,
    REQUIRED_PROVENANCE_DOCUMENTS,
    build_handoff_bundle,
    verify_handoff_bundle,
)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "configs/mlforecast",
        "docs/mlforecast",
        "src/loto/mlforecast",
        "tests/mlforecast",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_DOCUMENTS:
        (root / "docs" / "mlforecast" / name).write_text(
            f"# {name}\n",
            encoding="utf-8",
        )
    (root / "docs" / "mlforecast" / "FROZEN_BASE_SHA").write_text(
        "d" * 40 + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "mlforecast" / "FROZEN_UPSTREAM.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (root / "configs" / "mlforecast" / "core.yaml").write_text("mode: core\n")
    (root / "src" / "loto" / "mlforecast" / "x.py").write_text("VALUE = 1\n")
    (root / "tests" / "mlforecast" / "test_x.py").write_text("def test_x(): pass\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    (root / "uv.lock").write_text("version = 1\n")
    return root


def _build(tmp_path: Path):
    root = _repo(tmp_path)
    return build_handoff_bundle(
        root,
        tmp_path / "out",
        source_commit="a" * 40,
        source_branch="feature/test",
        committed_at="2026-08-05T00:00:00+00:00",
        validate_git=False,
    )


def test_handoff_bundle_contains_required_artifacts_and_verifies(tmp_path: Path) -> None:
    result = _build(tmp_path)
    verified = verify_handoff_bundle(result.zip_path, result.sha256_path)
    assert verified["status"] == "HANDOFF_VERIFIED"
    assert verified["source_commit"] == "a" * 40
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        for required in REQUIRED_DOCUMENTS + REQUIRED_PROVENANCE_DOCUMENTS:
            assert required in names
        assert "ARTIFACT_MANIFEST.json" in names
        assert "SHA256SUMS" in names


def test_handoff_bundle_is_deterministic(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first = build_handoff_bundle(
        root,
        tmp_path / "one",
        source_commit="b" * 40,
        source_branch="feature/test",
        committed_at="2026-08-05T00:00:00+00:00",
        validate_git=False,
    )
    second = build_handoff_bundle(
        root,
        tmp_path / "two",
        source_commit="b" * 40,
        source_branch="feature/test",
        committed_at="2026-08-05T00:00:00+00:00",
        validate_git=False,
    )
    assert first.sha256 == second.sha256
    assert first.zip_path.read_bytes() == second.zip_path.read_bytes()


def test_handoff_verifier_rejects_tampered_zip(tmp_path: Path) -> None:
    result = _build(tmp_path)
    payload = bytearray(result.zip_path.read_bytes())
    payload[-1] ^= 0x01
    result.zip_path.write_bytes(payload)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_handoff_bundle(result.zip_path, result.sha256_path)


def test_handoff_builder_requires_all_documents(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs" / "mlforecast" / "HANDOFF.md").unlink()
    with pytest.raises(RuntimeError, match="required handoff documents"):
        build_handoff_bundle(
            root,
            tmp_path / "out",
            source_commit="c" * 40,
            source_branch="feature/test",
            committed_at="2026-08-05T00:00:00+00:00",
            validate_git=False,
        )


def test_handoff_manifest_and_sums_agree(tmp_path: Path) -> None:
    result = _build(tmp_path)
    with zipfile.ZipFile(result.zip_path) as archive:
        manifest = json.loads(archive.read("ARTIFACT_MANIFEST.json"))
        sums = {
            name: digest
            for digest, name in (
                line.split("  ", 1)
                for line in archive.read("SHA256SUMS").decode().splitlines()
            )
        }
    expected = {record["path"]: record["sha256"] for record in manifest["artifacts"]}
    assert sums == expected


def _commit_repo(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "test"], check=True)


def test_git_backed_handoff_uses_only_tracked_files(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_repo(root)
    ignored = root / "src" / "loto" / "mlforecast" / "__pycache__" / "x.pyc"
    ignored.parent.mkdir()
    ignored.write_bytes(b"ignored")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "ignore cache"], check=True)
    result = build_handoff_bundle(root, tmp_path / "out-git")
    with zipfile.ZipFile(result.zip_path) as archive:
        assert not any(
            "__pycache__" in name or name.endswith(".pyc")
            for name in archive.namelist()
        )


def test_git_backed_handoff_rejects_dirty_scope(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_repo(root)
    (root / "docs" / "mlforecast" / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="handoff scope is dirty"):
        build_handoff_bundle(root, tmp_path / "out-dirty")
