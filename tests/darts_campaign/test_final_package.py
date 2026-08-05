from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from loto.darts_campaign.final_package import (
    FIXED_ZIP_TIME,
    HASHED_DOCUMENTS,
    NORMALIZED_MODE,
    REQUIRED_DOCUMENTS,
    FinalPackageConfig,
    FinalPackageError,
    build_final_package,
    build_manifest_entries,
    refresh_sha256s,
    render_sha256s,
    verify_sha256s,
    verify_zip_against_source,
)


def _documents(root: Path) -> Path:
    source = root / "docs"
    source.mkdir()
    for name in HASHED_DOCUMENTS:
        (source / name).write_text(f"# {name}\n\ncontract content for {name}\n", encoding="utf-8")
    (source / "SHA256SUMS").write_text("", encoding="utf-8")
    refresh_sha256s(source)
    return source


def _config(root: Path, source: Path, name: str = "handoff.zip") -> FinalPackageConfig:
    return FinalPackageConfig(
        package_id="darts-final-handoff-test",
        source_dir=source,
        output_zip=root / name,
        source_commit="b37dc3e463f95a1a8eced24cc99f4d14cc27fe67",
        base_commit="d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0",
        generated_at_utc="2026-08-05T10:50:00Z",
    )


def test_required_document_contract_is_exact() -> None:
    assert len(REQUIRED_DOCUMENTS) == 12
    assert REQUIRED_DOCUMENTS[-2:] == ("ARTIFACT_MANIFEST.md", "SHA256SUMS")
    assert HASHED_DOCUMENTS == REQUIRED_DOCUMENTS[:-1]


def test_refresh_and_verify_sha256s(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    entries = verify_sha256s(source)
    assert len(entries) == 11
    assert (source / "SHA256SUMS").read_text(encoding="utf-8") == render_sha256s(entries)


def test_missing_required_document_is_rejected(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    (source / "HANDOFF.md").unlink()
    with pytest.raises(FinalPackageError, match="required document is missing"):
        build_manifest_entries(source)


def test_unexpected_document_is_rejected(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    (source / "EXTRA.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(FinalPackageError, match="unexpected package documents"):
        build_manifest_entries(source)


def test_tampered_document_is_rejected(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    (source / "README.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FinalPackageError, match="SHA-256 mismatch"):
        verify_sha256s(source)


def test_deterministic_zip_is_byte_identical(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    first = build_final_package(_config(tmp_path, source, "first.zip"))
    second = build_final_package(_config(tmp_path, source, "second.zip"))
    assert first.verification.zip_sha256 == second.verification.zip_sha256
    assert (tmp_path / "first.zip").read_bytes() == (tmp_path / "second.zip").read_bytes()


def test_zip_member_order_timestamp_and_mode_are_normalized(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    build_final_package(_config(tmp_path, source))
    with zipfile.ZipFile(tmp_path / "handoff.zip", "r") as archive:
        assert tuple(item.filename for item in archive.infolist()) == REQUIRED_DOCUMENTS
        assert all(item.date_time == FIXED_ZIP_TIME for item in archive.infolist())
        assert all((item.external_attr >> 16) == NORMALIZED_MODE for item in archive.infolist())


def test_zip_verification_detects_modified_archive(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    build_final_package(_config(tmp_path, source))
    archive_path = tmp_path / "handoff.zip"
    payload = bytearray(archive_path.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    archive_path.write_bytes(payload)
    with pytest.raises((FinalPackageError, zipfile.BadZipFile, RuntimeError, OSError)):
        verify_zip_against_source(archive_path, source)


def test_stale_sha256s_blocks_packaging(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    (source / "README.md").write_text("changed after hashing\n", encoding="utf-8")
    with pytest.raises(FinalPackageError, match="SHA256SUMS is stale"):
        build_final_package(_config(tmp_path, source))


def test_output_inside_source_directory_is_rejected(tmp_path: Path) -> None:
    source = _documents(tmp_path)
    config = _config(tmp_path, source).model_copy(update={"output_zip": source / "handoff.zip"})
    with pytest.raises(FinalPackageError, match="outside the source"):
        build_final_package(config)
