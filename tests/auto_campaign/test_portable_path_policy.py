from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from loto.auto_campaign.portable_artifact import (
    _safe_relative,
    _write_deterministic_zip,
    verify_portable_bundle,
)


@pytest.mark.parametrize(
    "value",
    [
        "C:/Windows/system32/file.txt",
        "payload/CON",
        "payload/NUL.txt",
        "payload/trailing-dot.",
        "payload/trailing-space ",
        "payload/control-\x01.txt",
    ],
)
def test_nonportable_relative_paths_are_rejected(value: str) -> None:
    failures: list[str] = []

    result = _safe_relative(value, failures, "member")

    assert result is None
    assert failures == [f"member is unsafe: {value}"]


def test_case_insensitive_archive_collision_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "Alpha.txt").write_text("one", encoding="utf-8")
    (root / "alpha.txt").write_text("two", encoding="utf-8")
    if len(list(root.iterdir())) != 2:
        pytest.skip("filesystem is case-insensitive")

    with pytest.raises(ValueError, match="case-insensitive archive collision"):
        _write_deterministic_zip(root, tmp_path / "collision.zip")


def test_windows_drive_zip_member_is_rejected_before_extraction(tmp_path: Path) -> None:
    bundle = tmp_path / "drive.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("C:/escape.txt", "escape")

    result = verify_portable_bundle(bundle)

    assert result["status"] == "FAIL"
    assert any("ZIP member is unsafe" in failure for failure in result["failures"])
    assert not (tmp_path / "escape.txt").exists()
