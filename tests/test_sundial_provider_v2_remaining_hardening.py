from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from loto.models.providers import sundial as adapter

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_script(
    "sundial_provider_v2_hardened_runner",
    ROOT / "scripts" / "run_sundial_provider.py",
)
VERIFIER = _load_script(
    "sundial_provider_v2_hardened_verifier",
    ROOT / "scripts" / "verify_sundial_provider_v2_evidence.py",
)


@pytest.mark.parametrize("value", [3, 3.0, "3", np.int64(3), np.float64(3.0)])
def test_integral_sample_counts_are_accepted(value: Any) -> None:
    assert RUNNER._normalize_num_samples(value) == 3
    assert adapter._normalize_num_samples(value) == 3


@pytest.mark.parametrize("value", [1.5, np.float64(2.5), "1.5", True, object()])
def test_fractional_or_non_integer_sample_counts_are_rejected(value: Any) -> None:
    with pytest.raises(RUNNER.SundialProviderRuntimeError) as runner_error:
        RUNNER._normalize_num_samples(value)
    assert runner_error.value.status == "INVALID_REQUEST"

    with pytest.raises(adapter.FoundationProviderError) as adapter_error:
        adapter._normalize_num_samples(value)
    assert adapter_error.value.status == "INVALID_REQUEST"


def test_missing_status_is_reported_as_structured_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "sundial-v2-20260806-010203"
    run_dir.mkdir()
    report = VERIFIER.verify_run(
        run_dir,
        repo_root=None,
        expected_commit="abc",
        expected_branch="feat/sundial-probabilistic-provider-v2",
    )
    assert report["status"] == "FAIL"
    assert report["reasons"] == ["STATUS_FILE_MISSING"]
    assert report["checksum_entry_count"] == 0


def test_semantic_report_is_embedded_in_evidence_zip(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    verification_dir = tmp_path / "verification"
    run_dir.mkdir()
    verification_dir.mkdir()
    (run_dir / "status.txt").write_text("PASS\n", encoding="utf-8")
    (verification_dir / "VERIFICATION_REPORT.json").write_text("{}\n", encoding="utf-8")
    semantic_report = tmp_path / "sundial-v2-20260806-010203.json"
    semantic_report.write_text('{"status":"PASS"}\n', encoding="utf-8")
    archive = tmp_path / "evidence.zip"

    VERIFIER.create_archive(
        run_dir,
        verification_dir,
        archive,
        semantic_reports=(semantic_report,),
    )

    with zipfile.ZipFile(archive) as bundle:
        assert f"semantic/{semantic_report.name}" in bundle.namelist()
    assert archive.with_suffix(".zip.sha256").is_file()


def test_final_and_package_gates_require_semantic_archive_evidence() -> None:
    final_gate = (ROOT / "scripts/run_sundial_provider_v2_final_gate.sh").read_text(
        encoding="utf-8"
    )
    package_gate = (ROOT / "scripts/package_sundial_provider_v2_evidence.sh").read_text(
        encoding="utf-8"
    )
    for text in (final_gate, package_gate):
        assert "--semantic-report" in text
        assert "semantic/" in text
    assert "archive-content-check" in final_gate
    assert "test_sundial_provider_v2_remaining_hardening.py" in final_gate
