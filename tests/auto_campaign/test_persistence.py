from pathlib import Path

from loto.auto_campaign.persistence import verify_sha256s, write_sha256s


def test_sha256_manifest_detects_change(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    write_sha256s(tmp_path)
    assert verify_sha256s(tmp_path) == []
    (tmp_path / "a.txt").write_text("b", encoding="utf-8")
    assert verify_sha256s(tmp_path) == ["mismatch:a.txt"]
