from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.probabilistic.models.kdpp_native import (
    GRAPH_ID,
    MODEL_ID,
    KDPPChronologyEvidence,
    KDPPDegeneracyStatus,
    KDPPExecutionPending,
    KDPPFixedKConfig,
    KDPPFixedKModelSkeleton,
    KDPPFixedKRequest,
    KDPPFixedKResponse,
    KDPPGame,
    KDPPKernelType,
    KDPPPointForecastSemantics,
    KDPPPSDRepairPolicy,
    KDPPTargetLayout,
    canonical_config_sha256,
    load_kdpp_fixed_k_config,
)

SHA = "a" * 64
GIT_SHA = "b" * 40


def chronology() -> KDPPChronologyEvidence:
    return KDPPChronologyEvidence(
        train_start=0,
        train_end=99,
        validation_start=100,
        validation_end=109,
        forecast_origin=110,
        future_actuals_available=False,
        known_future_covariates=("draw_weekday",),
        feature_cutoff=99,
        feature_matrix_sha256=SHA,
    )


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "run_id": "kdpp-contract-1",
        "model_id": MODEL_ID,
        "package_version": "3.2.0",
        "source_revision": GIT_SHA,
        "model_revision": GRAPH_ID,
        "config_sha256": SHA,
        "weight_sha256": None,
        "license": "MIT",
        "game": KDPPGame.MINILOTO,
        "target_layout": KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY,
        "context_length": 128,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "chronology_evidence": chronology(),
        "actuals_used": False,
        "kernel_type": KDPPKernelType.L_ENSEMBLE,
        "kernel_shape": (31, 31),
        "kernel_sha256": SHA,
        "item_ids": tuple(str(index) for index in range(1, 32)),
        "cardinality": 5,
        "psd_tolerance": 1e-10,
        "psd_repair_policy": KDPPPSDRepairPolicy.REJECT,
    }
    payload.update(overrides)
    return payload


def response_payload(**overrides: object) -> dict[str, object]:
    items = tuple(str(index) for index in range(1, 32))
    subset = ("1", "2", "3", "4", "5")
    marginals = tuple([5.0 / 31.0] * 31)
    payload: dict[str, object] = {
        **request_payload(),
        "weight_sha256": SHA,
        "effective_device": "cpu",
        "cpu_fallback": False,
        "input_shape": (31, 31),
        "output_shape": (1, 5),
        "point_forecast": (subset,),
        "quantiles": None,
        "samples": ((subset, ("6", "7", "8", "9", "10")),),
        "finite_check": True,
        "runtime_pid": 1234,
        "gpu_uuid": None,
        "gpu_process_vram_mb": None,
        "gpu_not_applicable": True,
        "artifact_paths": ("runtime/request.json", "runtime/response.json"),
        "symmetry_check": True,
        "psd_check": True,
        "minimum_eigenvalue": 0.1,
        "kernel_rank": 31,
        "effective_rank": 18.5,
        "log_normalizer": 4.2,
        "kernel_off_diagonal_norm": 2.0,
        "kernel_off_diagonal_ratio": 0.2,
        "degeneracy_status": KDPPDegeneracyStatus.DIVERSE_KERNEL,
        "marginal_inclusion_probabilities": (marginals,),
        "exact_cardinality_check": True,
        "duplicate_check": True,
        "point_forecast_semantics": KDPPPointForecastSemantics.SEEDED_EXACT_SAMPLE,
        "item_ids": items,
    }
    payload.update(overrides)
    return payload


def test_config_is_strict_and_not_public() -> None:
    config = KDPPFixedKConfig()
    assert config.model_id == MODEL_ID
    assert config.graph_id == GRAPH_ID
    assert config.public_registration is False
    assert config.runtime_status == "EXECUTION_PENDING"
    with pytest.raises(ValidationError):
        KDPPFixedKConfig.model_validate({"unknown": 1})


def test_model_id_schema_and_sha256_are_fixed() -> None:
    KDPPFixedKRequest.model_validate(request_payload())
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(model_id="pp-other"))
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(schema_version="2.0.0"))
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(config_sha256="A" * 64))


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(surprise=True))


@pytest.mark.parametrize("prediction_length", [1, 2, 5])
def test_supported_prediction_lengths(prediction_length: int) -> None:
    request = KDPPFixedKRequest.model_validate(
        request_payload(prediction_length=prediction_length)
    )
    assert request.prediction_length == prediction_length


@pytest.mark.parametrize("prediction_length", [0, 3, 4, 6])
def test_unsupported_prediction_lengths_are_rejected(prediction_length: int) -> None:
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(
            request_payload(prediction_length=prediction_length)
        )


def test_cpu_only_device_and_actuals_contract() -> None:
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(requested_device="cuda"))
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(actuals_used=True))
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(response_payload(gpu_uuid="GPU-1"))
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(response_payload(cpu_fallback=True))


def test_nan_and_inf_are_rejected() -> None:
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(psd_tolerance=math.nan))
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(
            response_payload(minimum_eigenvalue=math.inf)
        )


def test_numbers3_position_qualified_duplicates_are_not_global_digit_duplicates() -> None:
    item_ids = tuple(f"n{position}:{digit}" for position in range(1, 4) for digit in range(10))
    request = KDPPFixedKRequest.model_validate(
        request_payload(
            game=KDPPGame.NUMBERS3,
            target_layout=KDPPTargetLayout.POSITION_QUALIFIED_SHARED,
            item_ids=item_ids,
            cardinality=3,
            kernel_shape=(30, 30),
        )
    )
    assert "n1:7" in request.item_ids
    assert "n2:7" in request.item_ids


def test_numbers4_position_local_requires_one_position_and_k_one() -> None:
    item_ids = tuple(f"n2:{digit}" for digit in range(10))
    request = KDPPFixedKRequest.model_validate(
        request_payload(
            game=KDPPGame.NUMBERS4,
            target_layout=KDPPTargetLayout.POSITION_LOCAL,
            item_ids=item_ids,
            cardinality=1,
            kernel_shape=(10, 10),
        )
    )
    assert request.cardinality == 1
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(
            request_payload(
                game=KDPPGame.NUMBERS4,
                target_layout=KDPPTargetLayout.POSITION_LOCAL,
                item_ids=item_ids,
                cardinality=2,
                kernel_shape=(10, 10),
            )
        )


@pytest.mark.parametrize(
    ("game", "candidate_count", "cardinality"),
    [
        (KDPPGame.MINILOTO, 31, 5),
        (KDPPGame.LOTO6, 43, 6),
        (KDPPGame.LOTO7, 37, 7),
    ],
)
def test_unordered_game_geometry(
    game: KDPPGame, candidate_count: int, cardinality: int
) -> None:
    request = KDPPFixedKRequest.model_validate(
        request_payload(
            game=game,
            item_ids=tuple(str(index) for index in range(1, candidate_count + 1)),
            cardinality=cardinality,
            kernel_shape=(candidate_count, candidate_count),
        )
    )
    assert request.cardinality == cardinality


def test_kernel_shape_cardinality_and_psd_policy_fail_closed() -> None:
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(kernel_shape=(30, 30)))
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(cardinality=31))
    with pytest.raises(ValidationError):
        KDPPFixedKRequest.model_validate(request_payload(psd_repair_policy="REPAIR"))


def test_response_quantiles_semantics_and_safe_paths() -> None:
    response = KDPPFixedKResponse.model_validate(response_payload())
    assert response.quantiles is None
    assert response.point_forecast_semantics == "SEEDED_EXACT_KDPP_SAMPLE"
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(response_payload(quantiles={"0.5": [1]}))
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(
            response_payload(artifact_paths=("../escape.json",))
        )
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(
            response_payload(point_forecast=(("1", "1", "2", "3", "4"),))
        )


def test_diagonal_kernel_requires_degeneracy_status() -> None:
    response = KDPPFixedKResponse.model_validate(
        response_payload(
            kernel_off_diagonal_norm=0.0,
            kernel_off_diagonal_ratio=0.0,
            degeneracy_status=KDPPDegeneracyStatus.DEGENERATE,
        )
    )
    assert response.degeneracy_status == "DEGENERATE_TO_CONDITIONAL_BERNOULLI"
    with pytest.raises(ValidationError):
        KDPPFixedKResponse.model_validate(
            response_payload(
                kernel_off_diagonal_norm=0.0,
                kernel_off_diagonal_ratio=0.0,
                degeneracy_status=KDPPDegeneracyStatus.DIVERSE_KERNEL,
            )
        )


def test_config_hash_is_canonical_and_loader_matches(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "configs" / "probabilistic" / "k_dpp_fixed_k.yaml"
    config = load_kdpp_fixed_k_config(source)
    first = canonical_config_sha256(config)
    second = canonical_config_sha256(config.model_dump(mode="json"))
    assert first == second
    assert len(first) == 64

    reordered = tmp_path / "reordered.yaml"
    reordered.write_text(
        "model_id: pp-k-dpp-fixed-k\nschema_version: 1.0.0\n"
        "graph_id: k_dpp_fixed_k_v1\nmodel_revision: k_dpp_fixed_k_v1\n"
        "public_registration: false\nruntime_status: EXECUTION_PENDING\n"
        "comparison_model: pp-conditional-bernoulli-fixed-k\n"
        "kernel_type: L_ENSEMBLE\npsd_tolerance: 1.0e-10\n"
        "psd_repair_policy: REJECT\n"
        "supported_games: [numbers3, numbers4, miniloto, loto6, loto7]\n"
        "supported_prediction_lengths: [1, 2, 5]\nrequested_device: cpu\n"
        "quantiles_supported: false\n"
        "default_point_forecast_semantics: SEEDED_EXACT_KDPP_SAMPLE\n",
        encoding="utf-8",
    )
    assert canonical_config_sha256(load_kdpp_fixed_k_config(reordered)) == first


def test_skeleton_is_importable_but_runtime_operations_are_blocked() -> None:
    model = KDPPFixedKModelSkeleton()
    assert model.public_registration is False
    assert model.runtime_status == "EXECUTION_PENDING"
    assert "loto.probabilistic.math.kdpp" in model.reused_math_modules
    for method in (model.fit, model.predict, model.save):
        with pytest.raises(KDPPExecutionPending):
            method(None)
    with pytest.raises(KDPPExecutionPending):
        KDPPFixedKModelSkeleton.load("state")
