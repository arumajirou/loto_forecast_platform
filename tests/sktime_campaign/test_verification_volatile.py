from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loto.sktime_campaign.verification import VerificationError, verify_sha256sums


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_recursive_sha_ignores_only_declared_volatile_outputs(tmp_path: Path) -> None:
    stable = tmp_path / "stable.json"
    stable.write_text("{}\n", encoding="utf-8")
    nested_sha = tmp_path / "inventory" / "SHA256SUMS"
    nested_sha.parent.mkdir()
    nested_sha.write_text("provider evidence\n", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "certification.log").write_text("still growing\n", encoding="utf-8")
    (tmp_path / "verification.log").write_text("still growing\n", encoding="utf-8")
    (tmp_path / "exit_code.txt").write_text("0\n", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text(
        f"{_sha256(nested_sha)}  inventory/SHA256SUMS\n{_sha256(stable)}  stable.json\n",
        encoding="utf-8",
    )

    records = verify_sha256sums(tmp_path, recursive=True)

    assert [record["path"] for record in records] == [
        "inventory/SHA256SUMS",
        "stable.json",
    ]


def test_recursive_sha_rejects_unsealed_stable_file(tmp_path: Path) -> None:
    stable = tmp_path / "stable.json"
    stable.write_text("{}\n", encoding="utf-8")
    (tmp_path / "unexpected.txt").write_text("must be sealed\n", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text(
        f"{_sha256(stable)}  stable.json\n",
        encoding="utf-8",
    )

    with pytest.raises(VerificationError, match="coverage mismatch"):
        verify_sha256sums(tmp_path, recursive=True)
