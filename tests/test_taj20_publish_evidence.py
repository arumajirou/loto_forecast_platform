from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_audit" / "taj20_publish_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("taj20_publish_evidence", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_sha256s_accepts_matching_file(tmp_path: Path) -> None:
    module = load_module()
    payload = tmp_path / "payload.txt"
    payload.write_text("verified\n", encoding="utf-8")
    digest = module._sha256(payload)
    (tmp_path / "SHA256SUMS").write_text(
        f"{digest}  payload.txt\n",
        encoding="utf-8",
    )

    module._verify_sha256s(tmp_path)


def test_verify_sha256s_rejects_path_escape(tmp_path: Path) -> None:
    module = load_module()
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    digest = module._sha256(outside)
    (tmp_path / "SHA256SUMS").write_text(
        f"{digest}  ../outside.txt\n",
        encoding="utf-8",
    )

    with pytest.raises(module.PublishError, match="path escapes root"):
        module._verify_sha256s(tmp_path)


def test_latest_reverify_selects_latest_directory(tmp_path: Path) -> None:
    module = load_module()
    first = tmp_path / "unified-reverify-20260818-120000"
    latest = tmp_path / "unified-reverify-20260818-130000"
    first.mkdir()
    latest.mkdir()

    assert module._latest_reverify(tmp_path) == latest
