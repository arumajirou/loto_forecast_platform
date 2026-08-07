from __future__ import annotations

from pathlib import Path

import pytest

from loto.auto_campaign import portable_prediction_verification as portable
from loto.auto_campaign.persistence import write_json


def _extracted_bundle(tmp_path: Path, stage: str) -> Path:
    root = tmp_path / "bundle"
    target = root / "payload" / "target"
    target.mkdir(parents=True)
    write_json(
        root / "PORTABLE_MANIFEST.json",
        {
            "schema_version": "all-auto-portable-artifact-v1",
            "target_relative_path": "payload/target",
        },
    )
    write_json(target / "manifest.json", {"status": "PASS", "stage": stage})
    return root


def test_nonprospective_portable_bundle_remains_compatible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _extracted_bundle(tmp_path, "holdout")
    monkeypatch.setattr(
        portable,
        "verify_portable_bundle",
        lambda _bundle: {"status": "PASS", "failures": []},
    )

    result = portable.verify_portable_bundle_with_prediction_lock(root)

    assert result["status"] == "PASS"
    assert result["prediction_lock_verification"]["status"] == "NOT_APPLICABLE"


def test_prospective_portable_bundle_requires_prediction_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _extracted_bundle(tmp_path, "prospective")
    monkeypatch.setattr(
        portable,
        "verify_portable_bundle",
        lambda _bundle: {"status": "PASS", "failures": []},
    )

    result = portable.verify_portable_bundle_with_prediction_lock(root)

    assert result["status"] == "FAIL"
    assert result["prediction_lock_verification"]["status"] == "FAIL"
    assert any("prediction lock missing" in item for item in result["failures"])


def test_prediction_verification_is_skipped_when_base_portable_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def fail_if_called(_root: Path) -> dict[str, object]:
        nonlocal called
        called = True
        return {"status": "PASS", "failures": []}

    monkeypatch.setattr(
        portable,
        "verify_portable_bundle",
        lambda _bundle: {"status": "FAIL", "failures": ["portable SHA mismatch"]},
    )
    monkeypatch.setattr(portable, "_verify_extracted_prediction_lock", fail_if_called)

    result = portable.verify_portable_bundle_with_prediction_lock(tmp_path / "broken.zip")

    assert result["status"] == "FAIL"
    assert result["prediction_lock_verification"]["status"] == (
        "NOT_RUN_BASE_PORTABLE_FAILED"
    )
    assert called is False
