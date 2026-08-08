from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from loto.mlforecast.handoff import (
    OPTIONAL_DOCUMENTS,
    REQUIRED_DOCUMENTS,
    _zip_info,
)
from loto.mlforecast.handoff_guard import (
    REQUIRED_CONFIG_FILES,
    REQUIRED_OPERATIONAL_FILES,
    REQUIRED_SOURCE_FILES,
    REQUIRED_TEST_FILES,
    build_guarded_handoff,
    verify_guarded_handoff,
)
from loto.mlforecast.provenance import upstream_contract

EntryList = list[tuple[str, bytes]]


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for name in REQUIRED_DOCUMENTS:
        _write(root / "docs/mlforecast" / name, f"# {name}\n".encode())
    for name in OPTIONAL_DOCUMENTS:
        _write(root / "docs/mlforecast" / name, f"# {name}\n".encode())
    _write(root / "docs/mlforecast/FROZEN_BASE_SHA", ("d" * 40 + "\n").encode())
    frozen_upstream = upstream_contract() | {
        "pypi_upload_time_utc": "2026-07-10T00:52:25.071033Z",
        "release_date": "2026-07-10",
        "status": "TAG_API_AND_PYPI_DIGEST_VERIFIED / LOCAL_WHEEL_RUNTIME_PENDING",
        "verified_on": "2026-08-05",
        "wheel_filename": "mlforecast-1.1.0-py3-none-any.whl",
    }
    _write(
        root / "docs/mlforecast/FROZEN_UPSTREAM.json",
        (json.dumps(frozen_upstream, sort_keys=True) + "\n").encode(),
    )
    for path in REQUIRED_CONFIG_FILES:
        _write(root / path, b"mode: test\n")
    for path in REQUIRED_OPERATIONAL_FILES:
        _write(root / path, b"#!/usr/bin/env bash\n")
    for path in REQUIRED_SOURCE_FILES:
        _write(root / path, b"VALUE = 1\n")
    for path in REQUIRED_TEST_FILES:
        _write(root / path, b"def test_placeholder(): pass\n")
    _write(root / "pyproject.toml", b"[project]\nname='x'\n")
    _write(root / "uv.lock", b"version = 1\n")
    return root


def _commit_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "branch", "-M", "feature/test"],
        check=True,
    )


def _build(tmp_path: Path):
    root = _repo(tmp_path)
    _commit_repo(root)
    return build_guarded_handoff(root, tmp_path / "out")


def _rewrite_zip(
    zip_path: Path,
    sidecar: Path,
    mutate: Callable[[EntryList], EntryList],
) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        entries = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    entries = mutate(entries)
    temporary = zip_path.with_suffix(".rewrite")
    with zipfile.ZipFile(
        temporary,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, payload in sorted(entries):
            archive.writestr(_zip_info(name), payload)
    temporary.replace(zip_path)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")


def test_guarded_build_and_verify(tmp_path: Path) -> None:
    result = _build(tmp_path)
    verified = verify_guarded_handoff(result.zip_path, result.sha256_path)
    assert verified["status"] == "HANDOFF_VERIFIED"
    assert verified["source_commit"] == result.source_commit


def test_guarded_build_rejects_dirty_shared_snapshot(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_repo(root)
    (root / "pyproject.toml").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="handoff inputs are dirty"):
        build_guarded_handoff(root, tmp_path / "out-dirty")


def test_guarded_build_rejects_detached_head(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_repo(root)
    subprocess.run(
        ["git", "-C", str(root), "checkout", "--detach", "-q"],
        check=True,
    )
    with pytest.raises(RuntimeError, match="non-detached"):
        build_guarded_handoff(root, tmp_path / "out-detached")


def test_guarded_verify_rejects_unexpected_member(tmp_path: Path) -> None:
    result = _build(tmp_path)
    _rewrite_zip(
        result.zip_path,
        result.sha256_path,
        lambda entries: entries + [("unexpected.txt", b"oops")],
    )
    with pytest.raises(RuntimeError, match="file set differs"):
        verify_guarded_handoff(result.zip_path, result.sha256_path)


def test_guarded_verify_rejects_manifest_provenance_mismatch(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)

    def mutate(entries: EntryList) -> EntryList:
        output: EntryList = []
        for name, payload in entries:
            if name == "ARTIFACT_MANIFEST.json":
                manifest = json.loads(payload)
                manifest["source_commit"] = "b" * 40
                payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            output.append((name, payload))
        return output

    _rewrite_zip(result.zip_path, result.sha256_path, mutate)
    with pytest.raises(RuntimeError, match="disagrees"):
        verify_guarded_handoff(result.zip_path, result.sha256_path)


def test_guarded_verify_rejects_size_limit(tmp_path: Path) -> None:
    result = _build(tmp_path)
    with pytest.raises(RuntimeError, match="uncompressed-size limit"):
        verify_guarded_handoff(
            result.zip_path,
            result.sha256_path,
            max_uncompressed_bytes=1,
        )


def test_guarded_verify_rejects_non_portable_path(tmp_path: Path) -> None:
    result = _build(tmp_path)
    _rewrite_zip(
        result.zip_path,
        result.sha256_path,
        lambda entries: entries + [("C:evil", b"oops")],
    )
    with pytest.raises(RuntimeError, match="non-portable"):
        verify_guarded_handoff(result.zip_path, result.sha256_path)


def test_guarded_verify_rejects_zip_symlink(tmp_path: Path) -> None:
    result = _build(tmp_path)
    link = tmp_path / "handoff-link.zip"
    link.symlink_to(result.zip_path)
    with pytest.raises(RuntimeError, match="not a regular file"):
        verify_guarded_handoff(link, result.sha256_path)


def test_guarded_verify_rejects_frozen_upstream_mismatch(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)

    def mutate(entries: EntryList) -> EntryList:
        output: EntryList = []
        for name, payload in entries:
            if name == "FROZEN_UPSTREAM.json":
                payload = b"{}\n"
            output.append((name, payload))
        return output

    _rewrite_zip(result.zip_path, result.sha256_path, mutate)
    with pytest.raises(RuntimeError, match="manifest verification failed"):
        verify_guarded_handoff(result.zip_path, result.sha256_path)


def test_guarded_verify_rejects_multiline_sidecar(tmp_path: Path) -> None:
    result = _build(tmp_path)
    original = result.sha256_path.read_text(encoding="utf-8")
    result.sha256_path.write_text(original + "extra\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly one line"):
        verify_guarded_handoff(result.zip_path, result.sha256_path)
