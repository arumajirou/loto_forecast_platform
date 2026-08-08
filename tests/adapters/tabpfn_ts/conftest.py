from __future__ import annotations

from collections.abc import Sequence

import pytest

from loto.adapters.tabpfn_ts import (
    ArtifactReference,
    CandidateScore,
    CheckpointLane,
    Device,
    EffectiveArguments,
    FeatureManifest,
    ForecastValue,
    GameGeometry,
    GPUEvidence,
    HistorySeries,
    LicenseEvidence,
    ModelIdentity,
    OutputSelection,
    QuantileForecast,
    ResponseStatus,
    RuntimeEvidence,
    TabPFNTSRequestV2,
    TabPFNTSResponseV2,
    TaskFormulation,
    TimeSemantics,
)
from loto.adapters.tabpfn_ts.manifests import (
    V2_REPO_ID,
    V2_REVISION,
    V2_WEIGHT_FILENAME,
    V2_WEIGHT_SHA256,
)


def build_position_request(
    *,
    prediction_length: int = 1,
    task_formulation: TaskFormulation = TaskFormulation.POSITION_BATCH,
) -> TabPFNTSRequestV2:
    geometry = GameGeometry(
        game_id="toy3",
        position_count=3,
        candidate_min=0,
        candidate_max=9,
        selection_count=3,
        strictly_increasing=False,
    )
    series_ids = ["n1", "n2", "n3"]
    history = [
        HistorySeries(
            series_id=series_id,
            timestamps=["1", "2", "3"],
            values=[float(index), float(index + 1), float(index + 2)],
        )
        for index, series_id in enumerate(series_ids)
    ]
    return TabPFNTSRequestV2(
        run_id="test-request",
        checkpoint_lane=CheckpointLane.V2_REG_LEGACY,
        repo_id=V2_REPO_ID,
        revision=V2_REVISION,
        task_formulation=task_formulation,
        game_geometry=geometry,
        series_ids=series_ids,
        history=history,
        time_semantics=TimeSemantics.DRAW_SEQUENCE,
        feature_set_id="running-index",
        max_context_length=256,
        prediction_length=prediction_length,
        quantile_levels=[0.1, 0.5, 0.9],
        output_selection=OutputSelection.MEDIAN,
        device=Device.CPU,
    )


def build_position_response(
    *,
    task_formulation: TaskFormulation = TaskFormulation.POSITION_BATCH,
    prediction_length: int = 1,
    point_offset: float = 0.0,
    cuda: bool = False,
) -> TabPFNTSResponseV2:
    geometry = GameGeometry(
        game_id="toy3",
        position_count=3,
        candidate_min=0,
        candidate_max=9,
        selection_count=3,
        strictly_increasing=False,
    )
    series_ids = ["n1", "n2", "n3"]
    point_values = [
        ForecastValue(
            series_id=series_id,
            horizon_step=step,
            value=float(series_index * 10 + step) + point_offset,
        )
        for series_index, series_id in enumerate(series_ids)
        for step in range(1, prediction_length + 1)
    ]
    quantiles = [
        QuantileForecast(
            level=level,
            values=[
                ForecastValue(
                    series_id=value.series_id,
                    horizon_step=value.horizon_step,
                    value=value.value + delta,
                )
                for value in point_values
            ],
        )
        for level, delta in ((0.1, -1.0), (0.5, 0.0), (0.9, 1.0))
    ]
    device = Device.CUDA if cuda else Device.CPU
    device_name = "cuda:0" if cuda else "cpu"
    return TabPFNTSResponseV2(
        status=ResponseStatus.OK,
        model_identity=ModelIdentity(
            checkpoint_lane=CheckpointLane.V2_REG_LEGACY,
            repo_id=V2_REPO_ID,
            revision=V2_REVISION,
            checkpoint_filename=V2_WEIGHT_FILENAME,
            checkpoint_sha256=V2_WEIGHT_SHA256,
        ),
        effective_arguments=EffectiveArguments(
            game_geometry=geometry,
            max_context_length=256,
            effective_context_length=3,
            prediction_length=prediction_length,
            quantile_levels=[0.1, 0.5, 0.9],
            output_selection=OutputSelection.MEDIAN,
            feature_set_id="running-index",
            time_semantics=TimeSemantics.DRAW_SEQUENCE,
        ),
        task_formulation=task_formulation,
        point_forecast=point_values,
        point_method=OutputSelection.MEDIAN,
        quantiles=quantiles,
        series_identity=series_ids,
        prediction_index=list(range(1, prediction_length + 1)),
        feature_manifest=FeatureManifest(
            feature_set_id="running-index",
            generators=["RunningIndexFeature"],
            config_sha256="a" * 64,
            frequency_policy="one_period_per_draw",
            missing_period_policy="reject",
        ),
        runtime_evidence=RuntimeEvidence(
            provider_pid=123,
            separate_process_reload=True,
            reload_status="PASS",
            model_parameter_device=device_name,
            training_table_device=device_name,
            test_table_device=device_name,
            prediction_tensor_device=device_name,
        ),
        gpu_evidence=GPUEvidence(
            requested_device=device,
            effective_device=device,
            model_parameter_device=device_name,
            training_table_device=device_name,
            test_table_device=device_name,
            prediction_tensor_device=device_name,
            provider_pid=123,
            gpu_uuid="GPU-test" if cuda else None,
            vram_before_bytes=0,
            vram_peak_bytes=1024 if cuda else 0,
            vram_after_bytes=0,
            cpu_fallback=False,
        ),
        artifact_reference=ArtifactReference(
            weight_sha256=V2_WEIGHT_SHA256,
            config_sha256="a" * 64,
            prediction_sha256="b" * 64,
        ),
        license_evidence=LicenseEvidence(
            code_license="Apache-2.0",
            weight_license="Prior Labs License 1.1",
            attribution_required=True,
            license_accepted=True,
            production_champion_eligible=False,
        ),
    )


def build_candidate_response(
    scores: Sequence[float] = (-0.4, 0.2, 0.1, 0.9, -0.1),
) -> TabPFNTSResponseV2:
    geometry = GameGeometry(
        game_id="toy-candidate",
        position_count=2,
        candidate_min=1,
        candidate_max=5,
        selection_count=2,
        strictly_increasing=True,
    )
    return TabPFNTSResponseV2(
        status=ResponseStatus.OK,
        model_identity=ModelIdentity(
            checkpoint_lane=CheckpointLane.V2_REG_LEGACY,
            repo_id=V2_REPO_ID,
            revision=V2_REVISION,
            checkpoint_filename=V2_WEIGHT_FILENAME,
            checkpoint_sha256=V2_WEIGHT_SHA256,
        ),
        effective_arguments=EffectiveArguments(
            game_geometry=geometry,
            max_context_length=256,
            effective_context_length=3,
            prediction_length=1,
            quantile_levels=[0.1, 0.5, 0.9],
            output_selection=OutputSelection.MEDIAN,
            feature_set_id="legacy-candidate",
            time_semantics=TimeSemantics.CALENDAR_TIME,
        ),
        task_formulation=TaskFormulation.CANDIDATE_SCORE,
        point_method=OutputSelection.MEDIAN,
        raw_candidate_scores=[
            CandidateScore(candidate=candidate, raw_candidate_regression_score=score)
            for candidate, score in enumerate(scores, start=1)
        ],
        selected_candidates=[2, 4],
        series_identity=[f"candidate-{candidate:02d}" for candidate in range(1, 6)],
        prediction_index=[1],
        feature_manifest=FeatureManifest(
            feature_set_id="legacy-candidate",
            generators=["CalendarFeature"],
            config_sha256="a" * 64,
            frequency_policy="calendar_time",
            missing_period_policy="preserve",
        ),
        runtime_evidence=RuntimeEvidence(
            provider_pid=123,
            separate_process_reload=True,
            reload_status="PASS",
            model_parameter_device="cpu",
            training_table_device="cpu",
            test_table_device="cpu",
            prediction_tensor_device="cpu",
        ),
        gpu_evidence=GPUEvidence(
            requested_device=Device.CPU,
            effective_device=Device.CPU,
            model_parameter_device="cpu",
            training_table_device="cpu",
            test_table_device="cpu",
            prediction_tensor_device="cpu",
            provider_pid=123,
            vram_before_bytes=0,
            vram_peak_bytes=0,
            vram_after_bytes=0,
            cpu_fallback=False,
        ),
        artifact_reference=ArtifactReference(
            weight_sha256=V2_WEIGHT_SHA256,
            config_sha256="a" * 64,
            prediction_sha256="b" * 64,
        ),
        license_evidence=LicenseEvidence(
            code_license="Apache-2.0",
            weight_license="Prior Labs License 1.1",
            attribution_required=True,
            license_accepted=True,
            production_champion_eligible=False,
        ),
    )


@pytest.fixture
def position_request() -> TabPFNTSRequestV2:
    return build_position_request()


@pytest.fixture
def position_response() -> TabPFNTSResponseV2:
    return build_position_response()
