# ruff: noqa: E402
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
TEST_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
sys.path.insert(0, str(TEST_ROOT))

from hierarchicalforecast_target import constants as c
from hierarchicalforecast_target.constants import CertificationError
from hierarchicalforecast_target.integrity import checksums, compact_sha256
from hierarchicalforecast_target.package_verification import (
    verify_formal,
    verify_source_hashes,
)
from hierarchicalforecast_target.runtime_verification import verify_runtime_files
from hierarchicalforecast_target_fixtures import (
    make_success_bundle,
    refresh_runtime_integrity,
    sha,
    write_json,
)


def test_verify_formal_accepts_complete_bundle(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    result = verify_formal(payload, tmp_path, "a" * 40)
    assert result["summary"]["passed_cases"] == 40
    assert result["zip_member_count"] == 6
    assert result["method_partition"] == {
        "executed_cases": 24,
        "rejected_cases": 16,
    }


def test_verify_formal_rejects_bad_case_count(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    payload["certification"]["summary"]["passed_cases"] = 39
    with pytest.raises(CertificationError, match="summary mismatch"):
        verify_formal(payload, tmp_path, "a" * 40)


def test_verify_formal_rejects_sidecar_mismatch(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    Path(payload["package"]["sha256_sidecar"]).write_text("0" * 64 + "  bad.zip\n")
    with pytest.raises(CertificationError, match="sidecar"):
        verify_formal(payload, tmp_path, "a" * 40)


def test_verify_formal_rejects_missing_execution_evidence(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    run_dir = Path(payload["certification"]["run_directory"])
    method_path = run_dir / "METHOD_RESULTS.json"
    method_payload = json.loads(method_path.read_text(encoding="utf-8"))
    method_payload["results"][0]["result"]["actual_execution"] = False
    write_json(method_path, method_payload)
    refresh_runtime_integrity(run_dir)
    with pytest.raises(CertificationError, match="execution identity"):
        verify_formal(payload, tmp_path, "a" * 40)


def test_verify_formal_rejects_shape_evidence_drift(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    run_dir = Path(payload["certification"]["run_directory"])
    method_path = run_dir / "METHOD_RESULTS.json"
    method_payload = json.loads(method_path.read_text(encoding="utf-8"))
    method_payload["results"][0]["result"]["shape"] = [999, 4]
    write_json(method_path, method_payload)
    refresh_runtime_integrity(run_dir)
    with pytest.raises(CertificationError, match="shape evidence"):
        verify_formal(payload, tmp_path, "a" * 40)


def test_verify_runtime_files_rejects_duplicate_manifest_row(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    run_dir = Path(payload["certification"]["run_directory"])
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][2] = dict(manifest["files"][0])
    write_json(manifest_path, manifest)
    (run_dir / "SHA256SUMS").write_text(
        "".join(f"{sha(run_dir / name)}  {name}\n" for name in c.PRIMARY),
        encoding="utf-8",
    )
    with pytest.raises(CertificationError, match="duplicate artifact manifest"):
        verify_runtime_files(run_dir, run_dir.name)


@pytest.mark.skipif(os.name == "nt", reason="symlink permissions vary on Windows")
def test_verify_runtime_files_rejects_symlink(tmp_path: Path) -> None:
    payload = make_success_bundle(tmp_path)
    run_dir = Path(payload["certification"]["run_directory"])
    original = run_dir / "INPUT_EVIDENCE.json"
    external = tmp_path / "external-input.json"
    external.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(external)
    with pytest.raises(CertificationError, match="symbolic link"):
        verify_runtime_files(run_dir, run_dir.name)


def test_checksums_rejects_traversal(tmp_path: Path) -> None:
    path = tmp_path / "SHA256SUMS"
    path.write_text(f"{'0' * 64}  ../escape\n", encoding="utf-8")
    with pytest.raises(CertificationError, match="unsafe"):
        checksums(path, {"../escape"})


def test_verify_source_hashes_recomputes_current_files(tmp_path: Path) -> None:
    source_root = tmp_path / "repo"
    source_dir = source_root / "src/loto/reconciliation"
    source_dir.mkdir(parents=True)
    runtime_path = source_dir / "runtime_certification.py"
    hierarchy_path = source_dir / "hierarchy.py"
    runtime_path.write_text("runtime\n", encoding="utf-8")
    hierarchy_path.write_text("hierarchy\n", encoding="utf-8")
    expected = {
        "runtime_certification": sha(runtime_path),
        "hierarchy": sha(hierarchy_path),
    }
    evidence = {
        "source_sha256": expected,
        "code_sha256": compact_sha256(expected),
    }
    verify_source_hashes(evidence, source_root)
    hierarchy_path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(CertificationError, match="source-hash"):
        verify_source_hashes(evidence, source_root)
