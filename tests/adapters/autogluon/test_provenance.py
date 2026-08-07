from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from loto.adapters.autogluon.provenance import (
    ArtifactContextError,
    build_fit_context,
    canonical_sha256,
    model_identity_evidence,
    persist_fit_context,
    validate_saved_artifact_context,
)


def _timeline() -> list[dict]:
    return [
        {
            "source_index": 0,
            "source_order": 10,
            "source_timestamp": "2026-01-01",
            "synthetic_timestamp": "2000-01-01T00:00:00+00:00",
        },
        {
            "source_index": 1,
            "source_order": 11,
            "source_timestamp": "2026-01-08",
            "synthetic_timestamp": "2000-01-02T00:00:00+00:00",
        },
    ]


def _plan(model: str = "Naive") -> dict:
    payload = {
        "execution_mode": "explicit_single_model",
        "selected_model_ids": [model],
        "predictor_kwargs": {
            "target": "target",
            "prediction_length": 2,
            "freq": "D",
            "quantile_levels": [0.1, 0.5, 0.9],
        },
        "fit_kwargs": {"hyperparameters": {model: {}}, "random_seed": 1},
        "argument_ledger": [],
    }
    return {**payload, "plan_sha256": canonical_sha256(payload)}


def _persist(tmp_path: Path, *, model: str = "Naive") -> tuple[Path, dict]:
    timeline = _timeline()
    source_payload = [
        {
            "source_index": row["source_index"],
            "source_order": row["source_order"],
            "source_timestamp": row["source_timestamp"],
        }
        for row in timeline
    ]
    plan = _plan(model)
    context = build_fit_context(
        run_id="fit-run",
        request_payload={"run_id": "fit-run"},
        execution_plan=plan,
        timeline_mapping=timeline,
        source_order_sha256=canonical_sha256(source_payload),
        timeline_mapping_sha256=canonical_sha256(timeline),
        geometry_sha256="g" * 64,
        library_version="1.5.0",
        model_names=[model],
        model_best=model,
    )
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    persist_fit_context(artifact, context=context)
    return artifact, plan


def test_model_identity_accepts_hpo_and_refit_suffixes() -> None:
    evidence = model_identity_evidence(
        ["SeasonalNaive", "Theta"],
        ["SeasonalNaive/T1", "Theta_FULL", "WeightedEnsemble"],
    )
    assert evidence["verified"] is True
    assert evidence["missing_model_ids"] == []


def test_model_identity_rejects_missing_requested_model() -> None:
    evidence = model_identity_evidence(["Naive", "Theta"], ["Naive"])
    assert evidence["verified"] is False
    assert evidence["missing_model_ids"] == ["Theta"]


def test_saved_context_round_trip_is_valid(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    saved = validate_saved_artifact_context(
        artifact,
        current_execution_plan=plan,
        current_geometry_sha256="g" * 64,
        expected_library_version="1.5.0",
    )
    assert saved.context["runtime_snapshot"]["model_identity"]["verified"] is True
    assert Path(saved.artifacts["provider_context"]).is_file()


def test_load_rejects_different_model_identity(tmp_path: Path) -> None:
    artifact, _ = _persist(tmp_path)
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=_plan("Theta"),
            current_geometry_sha256="g" * 64,
            expected_library_version="1.5.0",
        )
    assert captured.value.code == "ARTIFACT_MODEL_ID_MISMATCH"


def test_load_rejects_geometry_mismatch(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=plan,
            current_geometry_sha256="x" * 64,
            expected_library_version="1.5.0",
        )
    assert captured.value.code == "ARTIFACT_GEOMETRY_MISMATCH"


def test_load_rejects_tampered_execution_plan(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    plan_path = artifact / "loto_execution_plan_v2.json"
    tampered = json.loads(plan_path.read_text())
    tampered["selected_model_ids"] = ["Theta"]
    plan_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=plan,
            current_geometry_sha256="g" * 64,
            expected_library_version="1.5.0",
        )
    assert captured.value.code == "ARTIFACT_CONTEXT_PLAN_MISMATCH"


def test_load_rejects_tampered_mapping(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    mapping_path = artifact / "loto_timeline_mapping_v2.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["mapping"][0]["source_order"] = 999
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=plan,
            current_geometry_sha256="g" * 64,
            expected_library_version="1.5.0",
        )
    assert captured.value.code == "ARTIFACT_CONTEXT_MAPPING_MISMATCH"


def test_load_rejects_library_version_mismatch(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=plan,
            current_geometry_sha256="g" * 64,
            expected_library_version="1.4.0",
        )
    assert captured.value.code == "ARTIFACT_LIBRARY_VERSION_MISMATCH"


def test_load_rejects_unverified_snapshot(tmp_path: Path) -> None:
    artifact, plan = _persist(tmp_path)
    context_path = artifact / "loto_provider_context_v2.json"
    context = json.loads(context_path.read_text())
    context["runtime_snapshot"]["model_identity"]["verified"] = False
    context_path.write_text(json.dumps(context), encoding="utf-8")
    with pytest.raises(ArtifactContextError) as captured:
        validate_saved_artifact_context(
            artifact,
            current_execution_plan=plan,
            current_geometry_sha256="g" * 64,
            expected_library_version="1.5.0",
        )
    assert captured.value.code == "ARTIFACT_MODEL_IDENTITY_UNVERIFIED"


def test_build_context_does_not_mutate_inputs() -> None:
    plan = _plan()
    original = deepcopy(plan)
    timeline = _timeline()
    source_payload = [
        {
            "source_index": row["source_index"],
            "source_order": row["source_order"],
            "source_timestamp": row["source_timestamp"],
        }
        for row in timeline
    ]
    build_fit_context(
        run_id="fit-run",
        request_payload={"run_id": "fit-run"},
        execution_plan=plan,
        timeline_mapping=timeline,
        source_order_sha256=canonical_sha256(source_payload),
        timeline_mapping_sha256=canonical_sha256(timeline),
        geometry_sha256="g" * 64,
        library_version="1.5.0",
        model_names=["Naive"],
        model_best="Naive",
    )
    assert plan == original
