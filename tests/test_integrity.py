"""One authoritative manifest; staleness must be detectable."""

import json

import pytest

from loto.verify.integrity import (
    MANIFEST_NAME,
    generate_manifest,
    iter_tracked_files,
    verify_manifest,
)


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.txt").write_text("data\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    cache = tmp_path / "pkg" / "__pycache__"
    cache.mkdir()
    (cache / "a.cpython-311.pyc").write_bytes(b"\x00\x01")
    return tmp_path


def test_generate_then_verify_is_clean(tree):
    generate_manifest(tree, release="test")
    report = verify_manifest(tree)
    assert report.ok and report.status == "VERIFIED"
    assert report.n_verified == report.n_tracked == 3


def test_caches_are_never_tracked(tree):
    assert not any("__pycache__" in p for p in iter_tracked_files(tree))


def test_modified_file_is_reported_as_modified(tree):
    generate_manifest(tree)
    (tree / "pkg" / "a.py").write_text("print('tampered')\n", encoding="utf-8")
    report = verify_manifest(tree)
    assert report.status == "MODIFIED"
    assert "pkg/a.py" in report.modified


def test_deleted_file_is_reported_as_missing_not_modified(tree):
    generate_manifest(tree)
    (tree / "pkg" / "b.txt").unlink()
    report = verify_manifest(tree)
    assert report.status == "INCOMPLETE"
    assert report.missing == ["pkg/b.txt"] and not report.modified


def test_added_file_is_reported_as_stale_manifest(tree):
    """This is the v2.1.0 failure mode: 14 mismatches that were staleness, not tampering."""
    generate_manifest(tree)
    (tree / "pkg" / "c.py").write_text("new\n", encoding="utf-8")
    report = verify_manifest(tree)
    assert report.status == "STALE_MANIFEST"
    assert report.untracked == ["pkg/c.py"]
    assert not report.modified and not report.missing


def test_untracked_can_be_tolerated_explicitly(tree):
    generate_manifest(tree)
    (tree / "extra.md").write_text("x\n", encoding="utf-8")
    assert verify_manifest(tree, strict_untracked=False).ok


def test_manifest_self_digest_detects_manifest_tampering(tree):
    generate_manifest(tree)
    path = tree / MANIFEST_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["files"]["pkg/a.py"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = verify_manifest(tree)
    assert not report.ok
    assert report.manifest_digest_expected != report.manifest_digest_actual


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="integrity manifest"):
        verify_manifest(tmp_path)


def test_generate_rejects_a_file_path(tree):
    with pytest.raises(NotADirectoryError):
        generate_manifest(tree / "README.md")
