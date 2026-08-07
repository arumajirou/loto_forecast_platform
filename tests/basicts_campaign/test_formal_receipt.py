from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.basicts_campaign import formal_receipt
from loto.basicts_campaign.formal_receipt import (
    FormalReceiptError,
    build_formal_receipt,
    verify_formal_receipt,
    write_formal_receipt,
)

COMMIT = "a" * 40


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "run-1"
    root.mkdir()
    (root / "FORMAL_P0_STATUS.json").write_text("{}\n", encoding="utf-8")
    (root / "FORMAL_P0_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (root / "SHA256SUMS").write_text(
        "1" * 64 + "  FORMAL_P0_STATUS.json\n",
        encoding="utf-8",
    )
    return root


def _patch(monkeypatch: pytest.MonkeyPatch, run_dir: Path) -> dict[str, Any]:
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "git_commit": COMMIT,
        "source_bundle": {"path": str(run_dir.resolve())},
    }
    monkeypatch.setattr(formal_receipt, "verify_formal_bundle", lambda path: report)
    monkeypatch.setattr(
        formal_receipt,
        "verify_recursive_sha256",
        lambda path: {
            "FORMAL_P0_STATUS.json": "1" * 64,
            "FORMAL_P0_MANIFEST.json": "2" * 64,
        },
    )
    return report


def test_build_receipt_anchors_complete_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    report = _patch(monkeypatch, run_dir)

    receipt = build_formal_receipt(run_dir, expected_git_commit=COMMIT)

    assert receipt["status"] == "PASS"
    assert receipt["expected_git_commit"] == COMMIT
    assert receipt["verification"] == report
    assert receipt["source_bundle"]["checksum_entries"] == 2
    assert len(receipt["source_bundle"]["bundle_fingerprint_sha256"]) == 64


def test_build_receipt_rejects_commit_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)

    with pytest.raises(FormalReceiptError, match="Git commit mismatch"):
        build_formal_receipt(run_dir, expected_git_commit="b" * 40)


def test_write_and_verify_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    receipt_path = tmp_path / "receipt.json"

    write_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)
    verified = verify_formal_receipt(
        run_dir,
        receipt_path,
        expected_git_commit=COMMIT,
    )

    assert verified["status"] == "PASS"
    assert receipt_path.with_suffix(".json.sha256").is_file()


def test_verify_receipt_rejects_receipt_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    receipt_path = tmp_path / "receipt.json"
    write_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["status"] = "FAILED"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FormalReceiptError, match="receipt SHA-256 mismatch"):
        verify_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)


def test_verify_receipt_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    receipt_path = tmp_path / "receipt.json"
    write_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)
    (run_dir / "FORMAL_P0_STATUS.json").write_text("changed\n", encoding="utf-8")

    with pytest.raises(FormalReceiptError, match="differs from recomputed"):
        verify_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)


def test_write_receipt_rejects_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FormalReceiptError, match="already exists"):
        write_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)


def test_write_receipt_must_be_outside_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)

    with pytest.raises(FormalReceiptError, match="outside the source bundle"):
        write_formal_receipt(
            run_dir,
            run_dir / "receipt.json",
            expected_git_commit=COMMIT,
        )


def test_build_receipt_rejects_invalid_expected_commit(tmp_path: Path) -> None:
    run_dir = _bundle(tmp_path)

    with pytest.raises(FormalReceiptError, match="expected Git commit is invalid"):
        build_formal_receipt(run_dir, expected_git_commit="main")


def test_build_receipt_rejects_source_bundle_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    link = tmp_path / "run-link"
    try:
        link.symlink_to(run_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(FormalReceiptError, match="source bundle path"):
        build_formal_receipt(link, expected_git_commit=COMMIT)


def test_verify_receipt_rejects_receipt_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _bundle(tmp_path)
    _patch(monkeypatch, run_dir)
    receipt_path = tmp_path / "receipt.json"
    write_formal_receipt(run_dir, receipt_path, expected_git_commit=COMMIT)
    link = tmp_path / "receipt-link.json"
    checksum_link = tmp_path / "receipt-link.json.sha256"
    try:
        link.symlink_to(receipt_path)
        checksum_link.symlink_to(receipt_path.with_suffix(".json.sha256"))
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(FormalReceiptError, match="symbolic link"):
        verify_formal_receipt(run_dir, link, expected_git_commit=COMMIT)
