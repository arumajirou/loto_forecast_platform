from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from loto.adapters.autogluon.contracts import ProviderRequestV2, ProviderResponseV2
from loto.adapters.autogluon.execution import build_execution_plan
from loto.adapters.autogluon.inventory import (
    SOURCE_ENSEMBLE_SPECS,
    SOURCE_MODEL_SPECS,
    discover_runtime_inventory,
)
from loto.adapters.autogluon.provenance import canonical_sha256
from loto.models.autogluon_shared import (
    AUTOGLUON_CONCURRENCY_LIMITS,
    AutoGluonSharedContractError,
    adapt_autogluon_provider_response,
    build_autogluon_provider_request,
    resolve_game_profile,
)
from loto.models.catalog import ModelSpec
from loto.models.catalog_full import autogluon_runtime_catalog
from loto.models.workers import PositionSeriesWorker


def _history(position_count: int, rows: int = 24) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for index in range(rows):
        row: dict[str, Any] = {
            "draw_no": index + 1,
            "draw_date": f"2026-01-{index + 1:02d}",
        }
        if position_count in {3, 4}:
            for position in range(1, position_count + 1):
                row[f"n{position}"] = (index + position) % 10
        else:
            for position in range(1, position_count + 1):
                row[f"n{position}"] = position + (index % 2)
        records.append(row)
    return pd.DataFrame(records)


@pytest.mark.parametrize(
    (
        "game_id",
        "position_count",
        "candidate_min",
        "candidate_max",
        "allow_duplicates",
        "sort_policy",
    ),
    [
        ("numbers3", 3, 0, 9, True, "preserve"),
        ("numbers4", 4, 0, 9, True, "preserve"),
        ("miniloto", 5, 1, 31, False, "ascending"),
        ("loto6", 6, 1, 43, False, "ascending"),
        ("loto7", 7, 1, 37, False, "ascending"),
    ],
)
def test_shared_worker_builds_canonical_game_geometry(
    tmp_path: Path,
    game_id: str,
    position_count: int,
    candidate_min: int,
    candidate_max: int,
    allow_duplicates: bool,
    sort_policy: str,
) -> None:
    columns = [f"n{index}" for index in range(1, position_count + 1)]
    profile = resolve_game_profile(columns, game_id=game_id)
    assert profile.candidate_min == candidate_min
    assert profile.candidate_max == candidate_max
    assert profile.allow_duplicates is allow_duplicates
    assert profile.sort_policy == sort_policy

    request = ProviderRequestV2.model_validate(
        build_autogluon_provider_request(
            _history(position_count),
            position_columns=columns,
            params={"game_id": game_id},
            requested_device="cpu",
            artifact_dir=tmp_path / game_id,
        )
    )
    assert request.schema_version == 2
    assert request.provider_version == 2
    assert request.geometry is not None
    assert request.geometry.game_id == game_id
    assert request.geometry.selection_count == position_count
    assert request.geometry.candidate_min == candidate_min
    assert request.geometry.candidate_max == candidate_max
    assert request.geometry.allow_duplicates is allow_duplicates
    assert request.geometry.sort_policy == sort_policy
    assert request.seed == 1


def test_game_identity_can_be_inferred_from_position_count(tmp_path: Path) -> None:
    request = ProviderRequestV2.model_validate(
        build_autogluon_provider_request(
            _history(7),
            position_columns=[f"n{index}" for index in range(1, 8)],
            params={},
            requested_device="cpu",
            artifact_dir=tmp_path / "loto7",
        )
    )
    assert request.geometry is not None
    assert request.geometry.game_id == "loto7"


@pytest.mark.parametrize(
    ("params", "mode", "model_ids"),
    [
        ({}, "preset_automl", ()),
        ({"model_ids": ["Naive"]}, "explicit_single_model", ("Naive",)),
        (
            {"model_ids": ["Naive", "Theta"], "enable_ensemble": True},
            "explicit_multi_model",
            ("Naive", "Theta"),
        ),
        (
            {
                "model_ids": ["SeasonalNaive"],
                "hyperparameters": {
                    "SeasonalNaive": {
                        "seasonal_period": {"__space__": "categorical", "choices": [1, 2]}
                    }
                },
                "hyperparameter_tune_kwargs": {
                    "num_trials": 2,
                    "scheduler": "local",
                    "searcher": "auto",
                },
            },
            "hpo_single_model",
            ("SeasonalNaive",),
        ),
    ],
)
def test_shared_worker_preserves_execution_modes(
    tmp_path: Path,
    params: dict[str, Any],
    mode: str,
    model_ids: tuple[str, ...],
) -> None:
    payload = build_autogluon_provider_request(
        _history(3),
        position_columns=["n1", "n2", "n3"],
        params={"game_id": "numbers3", **params},
        requested_device="cpu",
        artifact_dir=tmp_path / mode,
    )
    request = ProviderRequestV2.model_validate(payload)
    assert request.execution_mode.value == mode
    assert request.model_ids == model_ids
    assert request.seed == 1
    plan = build_execution_plan(request)
    assert plan.selected_model_ids == model_ids
    if model_ids:
        assert set(plan.fit_kwargs["hyperparameters"]) == set(model_ids)


def test_auto_and_hpo_seed_must_remain_one(tmp_path: Path) -> None:
    with pytest.raises(AutoGluonSharedContractError, match="seed=1"):
        build_autogluon_provider_request(
            _history(3),
            position_columns=["n1", "n2", "n3"],
            params={"game_id": "numbers3", "autogluon_seed": 2},
            requested_device="cpu",
            artifact_dir=tmp_path / "bad-seed",
        )


def test_concurrency_contract_is_fixed_at_8_2_1(tmp_path: Path) -> None:
    payload = build_autogluon_provider_request(
        _history(3),
        position_columns=["n1", "n2", "n3"],
        params={"game_id": "numbers3", **AUTOGLUON_CONCURRENCY_LIMITS},
        requested_device="cpu",
        artifact_dir=tmp_path / "ok",
    )
    assert payload["schema_version"] == 2
    with pytest.raises(AutoGluonSharedContractError, match="max_autogluon_jobs must remain 2"):
        build_autogluon_provider_request(
            _history(3),
            position_columns=["n1", "n2", "n3"],
            params={"game_id": "numbers3", "max_autogluon_jobs": 3},
            requested_device="cpu",
            artifact_dir=tmp_path / "bad",
        )


def _write_artifacts(artifact_dir: Path) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for key, filename in (
        ("provider_context", "loto_provider_context_v2.json"),
        ("execution_plan", "loto_execution_plan_v2.json"),
        ("timeline_mapping", "loto_timeline_mapping_v2.json"),
    ):
        path = artifact_dir / filename
        path.write_text("{}\n", encoding="utf-8")
        result[key] = str(path)
    return result


def _response_for_request(
    request_payload: dict[str, Any],
    *,
    resolved_device: str = "cpu",
    cpu_fallback: bool = False,
    gpu_used: bool = False,
    evidence_status: str = "PARTIAL",
    vram_peak_bytes: int | None = None,
) -> dict[str, Any]:
    request = ProviderRequestV2.model_validate(request_payload)
    assert request.geometry is not None
    assert request.artifact_dir is not None
    artifacts = _write_artifacts(Path(request.artifact_dir))
    predictions = []
    for position in range(1, request.geometry.selection_count + 1):
        predictions.append(
            {
                "item_id": f"position-{position}",
                "timestamp": "2026-02-01T00:00:00Z",
                "horizon_step": 1,
                "mean": float(position),
                "quantiles": {
                    str(level): float(position) + index / 10
                    for index, level in enumerate(request.predictor.quantile_levels)
                },
            }
        )
    hash_value = "a" * 64
    response = ProviderResponseV2(
        run_id=request.run_id,
        status="OK",
        operation=request.operation,
        predictions=predictions,
        artifacts=artifacts,
        metadata={
            "library": "autogluon.timeseries",
            "library_version": "1.5.0",
            "execution_mode": request.execution_mode.value,
            "selected_model_ids": list(request.model_ids),
            "observed_model_names": list(request.model_ids) or ["SeasonalNaive"],
            "model_identity_verified": True,
            "plan_sha256": hash_value,
            "request_sha256": canonical_sha256(request.model_dump(mode="json")),
            "saved_context_sha256": hash_value,
            "source_order_sha256": hash_value,
            "timeline_mapping_sha256": hash_value,
            "geometry_sha256": hash_value,
            "prediction_shape": [request.geometry.selection_count, 1],
            "prediction_random_seed": request.seed,
            "model_best": (request.model_ids[0] if request.model_ids else "SeasonalNaive"),
            "model_names": list(request.model_ids) or ["SeasonalNaive"],
            "finite": True,
        },
        runtime_evidence={
            "requested_device": request.requested_device.value,
            "resolved_device": resolved_device,
            "cuda_available": request.requested_device.value == "cuda",
            "gpu_used": gpu_used,
            "cpu_fallback": cpu_fallback,
            "pid": 4242,
            "vram_peak_bytes": vram_peak_bytes,
            "evidence_status": evidence_status,
        },
    )
    return response.model_dump(mode="json")


def test_response_adapter_preserves_hash_artifact_pid_and_concurrency_evidence(
    tmp_path: Path,
) -> None:
    params = {"game_id": "numbers3", "model_ids": ["Naive"]}
    request = build_autogluon_provider_request(
        _history(3),
        position_columns=["n1", "n2", "n3"],
        params=params,
        requested_device="cpu",
        artifact_dir=tmp_path / "artifact",
    )
    result = adapt_autogluon_provider_response(
        request,
        _response_for_request(request),
        params=params,
    )
    assert result.position_values == (1.0, 2.0, 3.0)
    assert result.metadata["protocol_version"] == 2
    assert result.metadata["selected_model_ids"] == ["Naive"]
    assert result.metadata["runtime_evidence"]["pid"] == 4242
    assert result.metadata["request_sha256"] == canonical_sha256(
        ProviderRequestV2.model_validate(request).model_dump(mode="json")
    )
    assert result.metadata["concurrency"] == AUTOGLUON_CONCURRENCY_LIMITS
    assert result.metadata["gpu_certified"] is False


def test_cuda_fallback_must_be_explicit(tmp_path: Path) -> None:
    params = {"game_id": "numbers3", "model_ids": ["Naive"]}
    request = build_autogluon_provider_request(
        _history(3),
        position_columns=["n1", "n2", "n3"],
        params=params,
        requested_device="cuda",
        artifact_dir=tmp_path / "fallback",
    )
    result = adapt_autogluon_provider_response(
        request,
        _response_for_request(request, resolved_device="cpu", cpu_fallback=True),
        params=params,
    )
    assert result.metadata["runtime_evidence"]["cpu_fallback"] is True
    assert result.metadata["gpu_certified"] is False

    with pytest.raises(AutoGluonSharedContractError, match="fallback"):
        adapt_autogluon_provider_response(
            request,
            _response_for_request(request, resolved_device="cpu", cpu_fallback=False),
            params=params,
        )


def test_unverified_gpu_execution_is_rejected(tmp_path: Path) -> None:
    params = {"game_id": "numbers3", "model_ids": ["Naive"]}
    request = build_autogluon_provider_request(
        _history(3),
        position_columns=["n1", "n2", "n3"],
        params=params,
        requested_device="cuda",
        artifact_dir=tmp_path / "gpu",
    )
    with pytest.raises(AutoGluonSharedContractError, match="GPU success"):
        adapt_autogluon_provider_response(
            request,
            _response_for_request(
                request,
                resolved_device="cuda",
                gpu_used=True,
                evidence_status="PARTIAL",
                vram_peak_bytes=1024,
            ),
            params=params,
        )


def test_production_worker_defaults_to_protocol_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ModelSpec(
        "autogluon-timeseries",
        "automl",
        "autogluon",
        "position_series",
        "TimeSeriesPredictor",
        package="autogluon",
    )
    worker = PositionSeriesWorker(
        spec,
        params={"game_id": "numbers3", "model_ids": ["Naive"]},
        seed=999,
        device="cpu",
        position_columns=["n1", "n2", "n3"],
    )
    captured: dict[str, Any] = {}

    def fake_invoke(request: dict[str, Any]) -> dict[str, Any]:
        captured.update(request)
        return _response_for_request(request)

    monkeypatch.setattr(worker, "_invoke_autogluon_subprocess", fake_invoke)
    output = worker._autogluon(_history(3))
    assert captured["schema_version"] == 2
    assert captured["provider_version"] == 2
    assert captured["seed"] == 1
    assert captured["model_ids"] == ["Naive"]
    assert output.position_values.tolist() == [1.0, 2.0, 3.0]
    assert output.metadata["protocol_version"] == 2


def test_legacy_protocol_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ModelSpec(
        "autogluon-timeseries",
        "automl",
        "autogluon",
        "position_series",
        "TimeSeriesPredictor",
        package="autogluon",
    )
    worker = PositionSeriesWorker(
        spec,
        params={"protocol_version": 1},
        device="cpu",
        position_columns=["n1", "n2", "n3"],
    )
    captured: dict[str, Any] = {}

    def fake_invoke(request: dict[str, Any]) -> dict[str, Any]:
        captured.update(request)
        return {
            "status": "OK",
            "predictions": [1.0, 2.0, 3.0],
            "properties": {"model_best": "Naive", "presets": "fast_training"},
        }

    monkeypatch.setattr(worker, "_invoke_autogluon_subprocess", fake_invoke)
    output = worker._autogluon(_history(3))
    assert captured["schema_version"] == 1
    assert output.metadata["protocol_version"] == 1
    assert output.metadata["compatibility_path"] is True


def test_load_predict_requires_and_preserves_artifact_dir(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "saved"
    params = {
        "game_id": "numbers3",
        "model_ids": ["Naive"],
        "operation": "load_predict",
    }
    request = ProviderRequestV2.model_validate(
        build_autogluon_provider_request(
            _history(3),
            position_columns=["n1", "n2", "n3"],
            params=params,
            requested_device="cpu",
            artifact_dir=artifact_dir,
        )
    )
    assert request.operation.value == "load_predict"
    assert request.artifact_dir == str(artifact_dir.resolve())


def _runtime_inventory():
    model_attrs = {spec.class_name: type(spec.class_name, (), {}) for spec in SOURCE_MODEL_SPECS}

    class ModelRegistry:
        @staticmethod
        def available_aliases() -> list[str]:
            return [spec.alias for spec in SOURCE_MODEL_SPECS]

    models_module = SimpleNamespace(ModelRegistry=ModelRegistry, **model_attrs)
    ensemble_by_name = {spec.selectable_name: spec for spec in SOURCE_ENSEMBLE_SPECS}

    def get_ensemble_class(name: str):
        spec = ensemble_by_name[name]
        return type(spec.expected_class_name, (), {})

    ensemble_module = SimpleNamespace(get_ensemble_class=get_ensemble_class)
    return discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )


def test_catalog_keeps_source_discovery_importability_and_certification_separate() -> None:
    static_rows = autogluon_runtime_catalog()
    assert len(static_rows) == len(SOURCE_MODEL_SPECS) == 29
    assert all(row["source_declared"] is True for row in static_rows)
    assert not any(row["runtime_discovered"] for row in static_rows)
    assert not any(row["runtime_importable"] for row in static_rows)
    assert not any(row["runtime_certified"] for row in static_rows)

    inventory = _runtime_inventory()
    rows = autogluon_runtime_catalog(
        inventory,
        certified_aliases={"Naive", "Theta", "SeasonalNaive"},
    )
    assert all(row["runtime_discovered"] for row in rows)
    assert all(row["runtime_importable"] for row in rows)
    certified = {row["alias"] for row in rows if row["runtime_certified"]}
    assert certified == {"Naive", "Theta", "SeasonalNaive"}
    assert all(row["inventory_sha256"] == inventory.inventory_sha256 for row in rows)


def test_catalog_rejects_certification_without_runtime_evidence() -> None:
    with pytest.raises(ValueError, match="without discovered/importable runtime evidence"):
        autogluon_runtime_catalog(certified_aliases={"Naive"})
