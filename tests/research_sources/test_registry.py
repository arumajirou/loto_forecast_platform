from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loto.research_sources import load_registry, registry_sha256, validation_report

REGISTRY = Path("configs/research_sources/registry.v1.json")
EXPECTED_IDS = {
    "granite-flowstate",
    "tempopfn-38m",
    "kairos-10m",
    "kairos-23m",
    "kairos-50m",
    "reverso-small",
    "granite-patchtst-fm",
    "lightgts",
    "super-linear",
    "method-raft",
    "method-ts-rag",
}


def test_initial_source_records_are_complete() -> None:
    registry = load_registry(REGISTRY)
    assert {record.source_id for record in registry.records} == EXPECTED_IDS


def test_initial_records_use_allowed_intake_statuses() -> None:
    registry = load_registry(REGISTRY)
    allowed = {
        "VERIFIED_FOR_INTAKE",
        "CONDITIONAL",
        "REMOTE_CODE_REVIEW_REQUIRED",
        "LICENSE_REVIEW_REQUIRED",
        "CHECKPOINT_REVIEW_REQUIRED",
        "NOT_RELEASED",
        "BLOCKED",
    }
    assert {record.verification.status.value for record in registry.records} <= allowed


def test_registry_hash_is_deterministic() -> None:
    first = registry_sha256(load_registry(REGISTRY))
    second = registry_sha256(load_registry(REGISTRY))
    assert first == second
    assert len(first) == 64
    assert first == first.lower()


def test_validation_report_is_non_promotional() -> None:
    report = validation_report(load_registry(REGISTRY))
    assert report["status"] == "VALID"
    assert report["runtime_success"] is False
    assert report["production_eligibility"] is False
    assert report["record_count"] == 11


def test_every_record_retains_explicit_non_claims() -> None:
    registry = load_registry(REGISTRY)
    for record in registry.records:
        assert not any(record.non_claims.model_dump().values())


def test_registry_does_not_import_active_catalogs() -> None:
    forbidden = {
        "loto.models.catalog",
        "loto.models.catalog_full",
        "loto.probabilistic.catalog",
    }
    modules_before = set(sys.modules)
    load_registry(REGISTRY)
    imported = set(sys.modules) - modules_before
    assert forbidden.isdisjoint(imported)


def test_cli_writes_valid_report(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "loto.research_sources.cli",
            str(REGISTRY),
            "--report",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "VALID"
    assert report["runtime_success"] is False
    assert report["production_eligibility"] is False
