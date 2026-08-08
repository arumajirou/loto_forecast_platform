from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.auto_campaign.lineage_pipeline import _verified_run_failures
from loto.auto_campaign.persistence import sha256_file, write_json, write_sha256s
from loto.auto_campaign.verification_seal import (
    verify_verification_seal,
    write_verification_seal,
)


def _run_root(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    root.mkdir()
    write_json(
        root / "manifest.json",
        {
            "status": "PASS",
            "stage": "hpo",
            "code_sha256": "code-v1",
            "data_sha256": "data-v1",
        },
    )
    write_json(root / "campaign_config.json", {"seed": 1})
    write_json(root / "data_contract.json", {"rows": 100})
    write_json(root / "VERIFICATION_REPORT.json", {"status": "PASS"})
    return root


def _pass_result() -> dict[str, object]:
    return {
        "status": "PASS",
        "run_manifest_status": "PASS",
        "coverage_state_verification": {"status": "NOT_APPLICABLE"},
        "promotion_gate_verification": {"status": "PASS"},
        "lineage_verification": {"status": "PASS"},
        "failures": [],
    }


def test_verification_seal_passes_for_unchanged_content(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    payload = write_verification_seal(root, _pass_result())
    write_sha256s(root)

    result = verify_verification_seal(root)

    assert payload is not None
    assert result["status"] == "PASS"
    assert result["content_sha256"] == payload["content_sha256"]
    assert result["failures"] == []


def test_resealing_same_content_preserves_timestamp_and_hash(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    first = write_verification_seal(root, _pass_result())
    first_file_sha = sha256_file(root / "VERIFICATION_SEAL.json")
    second = write_verification_seal(root, _pass_result())
    second_file_sha = sha256_file(root / "VERIFICATION_SEAL.json")

    assert first is not None and second is not None
    assert second["sealed_at"] == first["sealed_at"]
    assert second_file_sha == first_file_sha


def test_content_change_fails_even_after_sha256s_regeneration(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    write_verification_seal(root, _pass_result())
    write_sha256s(root)
    write_json(root / "campaign_config.json", {"seed": 999})
    write_sha256s(root)

    result = verify_verification_seal(root)
    input_failures = _verified_run_failures(root, "source run")

    assert result["status"] == "FAIL"
    assert any("content hash mismatch" in item for item in result["failures"])
    assert any("verification seal" in item for item in input_failures)


def test_failed_verification_preserves_previous_seal(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    write_verification_seal(root, _pass_result())
    before = (root / "VERIFICATION_SEAL.json").read_bytes()

    result = write_verification_seal(
        root,
        {"status": "FAIL", "failures": ["mutation detected"]},
    )

    assert result is None
    assert (root / "VERIFICATION_SEAL.json").read_bytes() == before


def test_seal_payload_is_nonempty_json(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    write_verification_seal(root, _pass_result())

    payload = json.loads((root / "VERIFICATION_SEAL.json").read_text(encoding="utf-8"))

    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "all-auto-verification-seal-v1"
    assert payload["content_file_count"] >= 3


def test_broken_symlink_is_rejected_before_sealing(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    (root / "broken-link").symlink_to(root / "missing-target")

    with pytest.raises(ValueError, match="does not allow symlinks"):
        write_verification_seal(root, _pass_result())
