from __future__ import annotations

from pathlib import Path

import pytest

from loto.neuralforecast.auto_segrnn.runtime_source import (
    SOURCE_PATHS,
    SourceIdentityError,
    canonical_source_tree_sha256,
    collect_source_inventory,
    materialize_source_snapshot,
    verify_git_checkout,
    verify_working_source,
)


def _repository(tmp_path: Path) -> Path:
    for index, relative_path in enumerate(SOURCE_PATHS):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"source-{index}\n", encoding="utf-8")
    return tmp_path


def _git_runner(expected_revision: str, *, dirty: bool = False):
    def run(_root: Path, arguments: list[str]) -> str:
        if arguments == ["rev-parse", "HEAD"]:
            return expected_revision
        if arguments == ["branch", "--show-current"]:
            return "feat/runtime"
        if arguments[0] == "status":
            return "?? unexpected.txt" if dirty else ""
        raise AssertionError(arguments)

    return run


def test_inventory_and_snapshot_roundtrip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repo")
    files = collect_source_inventory(repository)
    assert len(files) == len(SOURCE_PATHS)
    digest = canonical_source_tree_sha256(files)
    parent = tmp_path / "snapshots"
    parent.mkdir()
    snapshot = materialize_source_snapshot(
        repository,
        parent,
        source_revision="a" * 40,
        files=files,
    )
    assert snapshot.name == "a" * 40
    copied = collect_source_inventory(snapshot)
    assert canonical_source_tree_sha256(copied) == digest


def test_verify_working_source_checks_git_and_digest(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repo")
    files = collect_source_inventory(repository)
    digest = canonical_source_tree_sha256(files)
    verified = verify_working_source(
        repository,
        expected_revision="a" * 40,
        expected_tree_sha256=digest,
        command_runner=_git_runner("a" * 40),
    )
    assert verified == files
    with pytest.raises(SourceIdentityError, match="SHA-256 mismatch"):
        verify_working_source(
            repository,
            expected_revision="a" * 40,
            expected_tree_sha256="b" * 64,
            command_runner=_git_runner("a" * 40),
        )


def test_git_checkout_rejects_dirty_or_detached(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repo")
    with pytest.raises(SourceIdentityError, match="clean"):
        verify_git_checkout(
            repository,
            "a" * 40,
            command_runner=_git_runner("a" * 40, dirty=True),
        )

    def detached(_root: Path, arguments: list[str]) -> str:
        if arguments == ["rev-parse", "HEAD"]:
            return "a" * 40
        if arguments == ["branch", "--show-current"]:
            return ""
        return ""

    with pytest.raises(SourceIdentityError, match="detached"):
        verify_git_checkout(repository, "a" * 40, command_runner=detached)


def test_inventory_rejects_symlinked_source(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repo")
    target = repository / SOURCE_PATHS[0]
    external = tmp_path / "external.py"
    external.write_text("external\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(external)
    with pytest.raises(SourceIdentityError, match="symlink"):
        collect_source_inventory(repository)
