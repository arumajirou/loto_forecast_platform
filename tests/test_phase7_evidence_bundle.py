from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "phase7_holdout_runner" / "evidence_bundle.py"
LINUX_WRAPPER = ROOT / "tools" / "phase7-evidence.sh"
WINDOWS_WRAPPER = ROOT / "tools" / "phase7-evidence.cmd"


def load_module():
    spec = importlib.util.spec_from_file_location("phase7_evidence_bundle", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_member_validation_rejects_traversal_and_windows_paths() -> None:
    module = load_module()
    for name in ("../escape", "/absolute", "a/../b", r"a\b"):
        with pytest.raises(module.EvidenceBundleError):
            module.validate_archive_member_name(name)


def test_archive_member_validation_accepts_portable_relative_path() -> None:
    module = load_module()
    result = module.validate_archive_member_name(
        "automlforecast-phase6c-ensemble-freeze-20260818-101021/artifacts/CANDIDATE_FREEZE.json"
    )
    assert result.as_posix().endswith("CANDIDATE_FREEZE.json")


def test_scientific_hashes_remain_pinned() -> None:
    module = load_module()
    assert module.EXPECTED_RUNNER_SHA256 == (
        "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
    )
    assert module.EXPECTED_FREEZE_SHA256 == (
        "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
    )
    assert module.EXPECTED_DEVELOPMENT_SHA256 == (
        "f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
    )
    assert module.EXPECTED_CANONICAL_SHA256 == (
        "88fd7bf24d2864fce74e95bf6475ff4b0292446f1354d403105970d095d6592f"
    )


def test_linux_import_wrapper_is_explicit_and_non_searching() -> None:
    text = LINUX_WRAPPER.read_text(encoding="utf-8")
    assert "phase7_evidence" in text
    assert "evidence_bundle.py" in text
    assert " import --bundle " in text
    assert "find " not in text
    assert "NEXT=bash tools/phase7.sh holdout" in text


def test_windows_export_wrapper_uses_portable_bundle_tool() -> None:
    text = WINDOWS_WRAPPER.read_text(encoding="utf-8")
    assert "evidence_bundle.py" in text
    assert '"%SCRIPT%" export' in text
    assert "phase7-evidence.sh import" in text
