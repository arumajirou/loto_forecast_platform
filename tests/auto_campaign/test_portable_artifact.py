from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from loto.auto_campaign.contracts import CampaignStage
from loto.auto_campaign.lineage_integrity import write_run_lineage
from loto.auto_campaign.persistence import sha256_file, write_json, write_sha256s
from loto.auto_campaign.portable_artifact import (
    PORTABLE_MANIFEST,
    export_portable_bundle,
    verify_portable_bundle,
)
from loto.auto_campaign.verification_seal import write_verification_seal


def _pass_result(*, gated: bool) -> dict[str, object]:
    return {
        "status": "PASS",
        "run_manifest_status": "PASS",
        "coverage_state_verification": {"status": "NOT_APPLICABLE"},
        "promotion_gate_verification": {"status": "PASS" if gated else "NOT_APPLICABLE"},
        "lineage_verification": {"status": "PASS" if gated else "NOT_APPLICABLE"},
        "failures": [],
    }


def _seal(root: Path, *, gated: bool) -> None:
    write_json(root / "VERIFICATION_REPORT.json", _pass_result(gated=gated))
    payload = write_verification_seal(root, _pass_result(gated=gated))
    assert payload is not None
    write_sha256s(root)


def _coverage_run(root: Path) -> Path:
    root.mkdir()
    write_json(
        root / "manifest.json",
        {
            "schema_version": "all-auto-api-coverage-v1",
            "status": "PASS",
            "stage": "api-coverage",
            "coverage_state_status": "VERIFIED",
            "verification_status": "VERIFIED",
            "code_sha256": "coverage-code",
            "data_sha256": "coverage-data",
        },
    )
    write_json(root / "coverage.json", {"status": "VERIFIED", "models": 36})
    _seal(root, gated=False)
    return root


def _target_run(root: Path, coverage: Path) -> Path:
    root.mkdir()
    write_json(root / "campaign_config.json", {"seed": 1, "stage": "hpo"})
    write_json(root / "data_contract.json", {"status": "PASS", "rows": 100})
    gate = {
        "schema_version": "all-auto-promotion-gate-v1",
        "status": "PASS",
        "target_stage": "hpo",
        "requires_gpu_runtime": False,
        "coverage_evidence": {"status": "PASS"},
        "runtime_evidence": None,
        "failures": [],
    }
    write_json(root / "PROMOTION_GATE.json", gate)
    write_json(
        root / "manifest.json",
        {
            "schema_version": "all-auto-campaign-run-v1",
            "status": "PASS",
            "stage": "hpo",
            "run_id": root.name,
            "code_sha256": "code-v1",
            "data_sha256": "data-v1",
            "promotion_gate_status": "PASS",
            "promotion_gate_path": "PROMOTION_GATE.json",
            "promotion_gate": gate,
        },
    )
    result = write_run_lineage(
        run_root=root,
        target_stage=CampaignStage.HPO,
        source_run=None,
        predecessor_run=None,
        coverage_run=coverage,
        runtime_run=None,
    )
    assert result["lineage_status"] == "PASS"
    _seal(root, gated=True)
    return root


def _bundle_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    coverage = _coverage_run(tmp_path / "coverage")
    target = _target_run(tmp_path / "hpo", coverage)
    bundle = tmp_path / "portable.zip"
    return target, coverage, bundle


def test_export_and_verify_after_original_tree_is_removed(tmp_path: Path) -> None:
    target, coverage, bundle = _bundle_fixture(tmp_path)

    exported = export_portable_bundle(target, bundle)
    shutil.rmtree(target)
    shutil.rmtree(coverage)
    verified = verify_portable_bundle(bundle)

    assert exported["status"] == "PASS"
    assert exported["entry_count"] == 2
    assert verified["status"] == "PASS"
    assert verified["entry_count"] == 2
    assert verified["bundle_sha256"] == exported["bundle_sha256"]


def test_same_sealed_tree_produces_identical_zip_bytes(tmp_path: Path) -> None:
    target, _coverage, first = _bundle_fixture(tmp_path)
    second = tmp_path / "portable-second.zip"

    first_result = export_portable_bundle(target, first)
    second_result = export_portable_bundle(target, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_result["bundle_sha256"] == second_result["bundle_sha256"]


def test_manifest_uses_safe_relative_relocation_paths(tmp_path: Path) -> None:
    target, _coverage, bundle = _bundle_fixture(tmp_path)
    export_portable_bundle(target, bundle)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)

    manifest = json.loads((extracted / PORTABLE_MANIFEST).read_text(encoding="utf-8"))

    assert manifest["target_relative_path"] == "payload/target"
    assert manifest["relocation_map"][str(target.resolve())] == "payload/target"
    assert all(not Path(value).is_absolute() for value in manifest["relocation_map"].values())
    assert all(".." not in Path(value).parts for value in manifest["relocation_map"].values())


def test_payload_mutation_fails_even_when_zip_is_recreated(tmp_path: Path) -> None:
    target, _coverage, bundle = _bundle_fixture(tmp_path)
    export_portable_bundle(target, bundle)
    extracted = tmp_path / "mutated"
    extracted.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)
    write_json(extracted / "payload/target/campaign_config.json", {"seed": 999})
    mutated = tmp_path / "mutated.zip"
    with zipfile.ZipFile(mutated, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in extracted.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(extracted).as_posix())

    result = verify_portable_bundle(mutated)

    assert result["status"] == "FAIL"
    assert any(
        "portable-sums mismatch:payload/target/campaign_config.json" in failure
        for failure in result["failures"]
    )


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "traversal.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.txt", "escape")

    result = verify_portable_bundle(bundle)

    assert result["status"] == "FAIL"
    assert any("ZIP member is unsafe" in failure for failure in result["failures"])
    assert not (tmp_path / "escape.txt").exists()


def test_output_inside_source_run_is_rejected_without_mutation(tmp_path: Path) -> None:
    target, _coverage, _bundle = _bundle_fixture(tmp_path)
    unexpected_parent = target / "new-export-directory"
    output = unexpected_parent / "portable.zip"

    with pytest.raises(ValueError, match="must not be inside a source run"):
        export_portable_bundle(target, output)

    assert not output.exists()
    assert not unexpected_parent.exists()


def test_source_symlink_is_rejected(tmp_path: Path) -> None:
    target, _coverage, bundle = _bundle_fixture(tmp_path)
    link = target / "unexpected-link"
    try:
        link.symlink_to(target / "campaign_config.json")
    except OSError:
        pytest.skip("symlinks are unavailable in this environment")

    with pytest.raises(ValueError, match="does not allow symlinks"):
        export_portable_bundle(target, bundle)


def test_bundle_sha_changes_when_zip_bytes_change(tmp_path: Path) -> None:
    target, _coverage, bundle = _bundle_fixture(tmp_path)
    result = export_portable_bundle(target, bundle)
    before = result["bundle_sha256"]
    bundle.write_bytes(bundle.read_bytes() + b"trailing-data")

    assert sha256_file(bundle) != before
