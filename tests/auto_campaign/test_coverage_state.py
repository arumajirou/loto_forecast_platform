from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.auto_campaign.coverage_state import (
    VerificationStatus,
    build_constructor_contract_matrix,
    resolve_argument_catalog,
    summarize_resolved_catalog,
    write_coverage_state_bundle,
)


def _catalog() -> list[dict[str, object]]:
    return [
        {
            "layer": "BaseAuto",
            "argument": "cls_model",
            "primary_value": "registry",
            "alternate_values": (),
            "status": "PLANNED",
            "note": "constructor inventory",
        },
        {
            "layer": "BaseAuto",
            "argument": "h",
            "primary_value": 1,
            "alternate_values": (5,),
            "status": "PLANNED",
            "note": "runtime case",
        },
        {
            "layer": "fit",
            "argument": "distributed_config",
            "primary_value": None,
            "alternate_values": ("Spark",),
            "status": "PLANNED",
            "note": "not locally applicable",
        },
    ]


def _constructor_rows(status: str = "VERIFIED") -> list[dict[str, object]]:
    return [
        {
            "name": "AutoA",
            "verification_status": status,
        },
        {
            "name": "AutoB",
            "verification_status": status,
        },
    ]


def test_resolve_argument_catalog_combines_runtime_and_constructor_evidence() -> None:
    results = [
        {
            "case": {
                "case_id": "base-h-5",
                "layer": "BaseAuto",
                "argument": "h",
                "expected": "PASS",
            },
            "status": "EXECUTED",
        },
        {
            "case.case_id": "fit-distributed-config",
            "case.layer": "fit",
            "case.argument": "distributed_config",
            "case.expected": "NOT_APPLICABLE",
            "status": "NOT_APPLICABLE",
        },
    ]

    rows = resolve_argument_catalog(
        results,
        catalog=_catalog(),
        constructor_matrix=_constructor_rows(),
    )
    by_key = {(row["layer"], row["argument"]): row for row in rows}

    assert by_key[("BaseAuto", "cls_model")]["verification_status"] == "VERIFIED"
    assert by_key[("BaseAuto", "h")]["verification_status"] == "VERIFIED"
    assert by_key[("fit", "distributed_config")]["verification_status"] == "VERIFIED"
    assert by_key[("BaseAuto", "h")]["case_ids"] == ["base-h-5"]
    assert summarize_resolved_catalog(rows)["overall_status"] == "VERIFIED"


def test_failed_or_unknown_case_status_fails_closed() -> None:
    failed = resolve_argument_catalog(
        [
            {
                "case": {
                    "case_id": "base-h-5",
                    "layer": "BaseAuto",
                    "argument": "h",
                },
                "status": "FAILED",
            }
        ],
        catalog=_catalog(),
        constructor_matrix=_constructor_rows(),
    )
    assert summarize_resolved_catalog(failed)["overall_status"] == "FAILED"

    unknown = resolve_argument_catalog(
        [
            {
                "case": {
                    "case_id": "base-h-5",
                    "layer": "BaseAuto",
                    "argument": "h",
                },
                "status": "MAYBE",
            }
        ],
        catalog=_catalog(),
        constructor_matrix=_constructor_rows(),
    )
    row = next(item for item in unknown if item["argument"] == "h")
    assert row["verification_status"] == "FAILED"
    assert row["unrecognized_case_statuses"] == ["MAYBE"]


def test_duplicate_case_ids_are_rejected() -> None:
    row = {
        "case": {
            "case_id": "duplicate",
            "layer": "BaseAuto",
            "argument": "h",
        },
        "status": "EXECUTED",
    }
    with pytest.raises(ValueError, match="duplicate API coverage case_id"):
        resolve_argument_catalog([row, row], catalog=_catalog())


def test_real_constructor_signature_matrix_covers_all_36_automodels() -> None:
    rows = build_constructor_contract_matrix(
        expected_model_count=36,
        probe_default_configs=False,
    )

    assert len(rows) == 36
    assert len({row["name"] for row in rows}) == 36
    assert all(row["constructor_has_h"] for row in rows)
    assert all(row["constructor_has_config"] for row in rows)
    assert all(row["verification_status"] == "PARTIALLY_VERIFIED" for row in rows)
    hint = next(row for row in rows if row["name"] == "AutoHINT")
    assert hint["supported_backends"] == ("ray",)
    assert hint["optuna_default_config_status"] == "NOT_APPLICABLE"


def test_write_bundle_marks_gpu_runtime_pending(monkeypatch, tmp_path: Path) -> None:
    fake_matrix = [
        {
            "name": "AutoA",
            "supported_backends": ("ray", "optuna"),
            "backend_results": {
                "ray": {"status": "VERIFIED"},
                "optuna": {"status": "VERIFIED"},
            },
            "verification_status": "VERIFIED",
        }
    ]
    monkeypatch.setattr(
        "loto.auto_campaign.coverage_state.build_constructor_contract_matrix",
        lambda **_kwargs: fake_matrix,
    )
    output = tmp_path / "coverage"

    manifest = write_coverage_state_bundle(
        output_dir=output,
        api_results=[],
        expected_model_count=1,
        probe_default_configs=False,
    )

    assert manifest["status"] == VerificationStatus.PARTIALLY_VERIFIED.value
    assert manifest["gpu_runtime_status"] == VerificationStatus.EXECUTION_PENDING.value
    assert (output / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv").is_file()
    assert (output / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet").is_file()
    assert (output / "API_ARGUMENT_COVERAGE_RESOLVED.csv").is_file()
    assert (output / "API_ARGUMENT_COVERAGE_RESOLVED.parquet").is_file()
    assert (output / "SHA256SUMS").is_file()
    persisted = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["gpu_runtime_status"] == "EXECUTION_PENDING"
