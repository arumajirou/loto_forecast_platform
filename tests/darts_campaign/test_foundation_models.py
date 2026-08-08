from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from loto.darts_campaign.foundation_models import (
    FOUNDATION_CAPABILITIES,
    FOUNDATION_MODEL_IDENTITIES,
    FoundationCampaignConfig,
    FoundationModelConfig,
    FoundationSourceConfig,
    FoundationSourceObservation,
    FoundationTrackObservation,
    capability_matrix_sha256,
    certify_capabilities,
    certify_source,
    certify_track,
    run_foundation_matrix,
)
from loto.darts_campaign.protocol import GameGeometry
from loto.darts_campaign.torch_models import TorchRuntimeObservation


class FakeSeries:
    def __init__(self, values: np.ndarray) -> None:
        self.data = np.asarray(values, dtype=float)

    @classmethod
    def from_series(cls, series: pd.Series) -> FakeSeries:
        return cls(series.to_numpy(float))

    @classmethod
    def from_dataframe(cls, frame: pd.DataFrame) -> FakeSeries:
        return cls(frame.to_numpy(float))


class FakeFoundation:
    supports_past_covariates = False
    supports_future_covariates = False
    supports_multivariate = True
    supports_probabilistic_prediction = True

    def __init__(
        self,
        input_chunk_length: int | tuple[int, int],
        output_chunk_length: int,
        output_chunk_shift: int = 0,
        hub_model_name: str = "model",
        hub_model_revision: str = "revision",
        local_dir: str | None = None,
        enable_finetuning: bool | dict = False,
        pl_trainer_kwargs: dict | None = None,
        accept_license: bool = False,
        **kwargs: object,
    ) -> None:
        self.input_chunk_length = input_chunk_length
        self.output_chunk_length = output_chunk_length
        self.output_chunk_shift = output_chunk_shift
        self.hub_model_name = hub_model_name
        self.hub_model_revision = hub_model_revision
        self.local_dir = local_dir
        self.enable_finetuning = enable_finetuning
        self.pl_trainer_kwargs = pl_trainer_kwargs
        self.accept_license = accept_license
        self.fit_series = None

    def fit(
        self,
        series: FakeSeries | list[FakeSeries],
        past_covariates: object | None = None,
        future_covariates: object | None = None,
    ) -> FakeFoundation:
        self.fit_series = series
        return self

    def predict(
        self,
        n: int,
        series: FakeSeries | list[FakeSeries],
        num_samples: int = 1,
        predict_likelihood_parameters: bool = False,
        past_covariates: object | None = None,
        future_covariates: object | None = None,
    ) -> object:
        if isinstance(series, list):
            return [np.arange(n, dtype=float) + index for index, _ in enumerate(series)]
        if series.data.ndim == 2:
            positions = series.data.shape[1]
            return np.arange(
                positions * n,
                dtype=float,
            ).reshape(n, positions)
        return np.arange(n, dtype=float)


class FakeChronos(FakeFoundation):
    supports_past_covariates = True
    supports_future_covariates = True


class FakeTimesFM(FakeFoundation):
    pass


class FakeTiRex(FakeFoundation):
    pass


class FakePatch(FakeFoundation):
    pass


MODELS = SimpleNamespace(
    Chronos2Model=FakeChronos,
    TimesFM2p5Model=FakeTimesFM,
    TiRexModel=FakeTiRex,
    PatchTSTFMModel=FakePatch,
)


def geometry() -> GameGeometry:
    return GameGeometry(
        game_id="numbers3",
        positions=3,
        min_value=0,
        max_value=9,
        draw_no_col="draw_no",
        position_prefix="N",
    )


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": list(range(1, 33)),
            "N1": [index % 10 for index in range(32)],
            "N2": [(index + 1) % 10 for index in range(32)],
            "N3": [(index + 2) % 10 for index in range(32)],
        }
    )


def source(
    name: str,
    revision: str = "a" * 40,
) -> FoundationSourceConfig:
    return FoundationSourceConfig(
        hub_model_name=f"provider/{name}",
        hub_model_revision=revision,
        local_dir=f"/models/{name}",
        allow_remote_download=False,
    )


def model(
    name: str,
    *,
    finetuning: bool | dict = False,
) -> FoundationModelConfig:
    args: dict[str, object] = {}
    accept = name == "TiRexModel"
    if name == "TiRexModel" and finetuning:
        args["tirex_kwargs"] = {"backend": "torch"}
    return FoundationModelConfig(
        public_name=name,
        source=source(name),
        accept_license=accept,
        finetuning=finetuning,
        model_args=args,
    )


def campaign(
    *,
    names: tuple[str, ...] = FOUNDATION_MODEL_IDENTITIES,
    track: str = "zero_shot",
    finetuning: bool | dict = False,
    layout: str = "position_global_sequence",
    use_past: bool = False,
    use_future: bool = False,
) -> FoundationCampaignConfig:
    return FoundationCampaignConfig(
        run_id="p8-test",
        track=track,
        models=tuple(model(name, finetuning=finetuning) for name in names),
        input_chunk_length=(8, 24),
        output_chunk_length=3,
        output_chunk_shift=0,
        series_layout=layout,
        horizon=3,
        use_past_covariates=use_past,
        use_future_covariates=use_future,
        device={
            "requested_accelerator": "gpu",
            "devices": [0],
            "allow_cpu_fallback": False,
            "require_gpu_pid": True,
            "require_vram_evidence": True,
        },
    )


def source_probe(
    item: FoundationModelConfig,
    runtime_model: object | None,
) -> FoundationSourceObservation:
    return FoundationSourceObservation(
        source_kind="local",
        resolved_revision=item.source.hub_model_revision,
        local_dir_exists=True,
        local_manifest_sha256="b" * 64,
        files_count=4,
        total_bytes=1024,
        download_performed=False,
        cache_hit=False,
    )


def zero_shot_probe(
    name: str,
    runtime_model: object,
) -> FoundationTrackObservation:
    return FoundationTrackObservation(
        enable_finetuning_effective=False,
        optimizer_steps=0,
        parameters_changed=False,
    )


def fine_tune_probe(
    name: str,
    runtime_model: object,
) -> FoundationTrackObservation:
    return FoundationTrackObservation(
        enable_finetuning_effective=True,
        optimizer_steps=3,
        parameters_changed=True,
    )


def gpu_probe(
    name: str,
    runtime_model: object,
    prediction: object,
    position: int | None,
) -> TorchRuntimeObservation:
    return TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="gpu",
        effective_accelerator="gpu",
        model_parameter_devices=("cuda:0",),
        prediction_device="cuda:0",
        process_pid=100,
        gpu_pid=100,
        device_index=0,
        vram_before_bytes=100,
        vram_peak_bytes=300,
        vram_after_bytes=200,
        cuda_allocated_bytes=120,
        cuda_reserved_bytes=180,
    )


def test_foundation_identity_and_capability_matrix_is_stable() -> None:
    assert FOUNDATION_MODEL_IDENTITIES == (
        "Chronos2Model",
        "TimesFM2p5Model",
        "TiRexModel",
        "PatchTSTFMModel",
    )
    assert FOUNDATION_CAPABILITIES["Chronos2Model"].supports_past_covariates
    assert not FOUNDATION_CAPABILITIES["TimesFM2p5Model"].supports_past_covariates
    assert len(capability_matrix_sha256()) == 64


def test_offline_source_requires_local_directory_and_revision() -> None:
    with pytest.raises(ValidationError):
        FoundationSourceConfig(
            hub_model_name="amazon/chronos-2",
            hub_model_revision="a" * 40,
            allow_remote_download=False,
        )
    unresolved = source("Chronos2Model", "UNRESOLVED")
    branch_name = source("Chronos2Model", "main")
    assert not unresolved.revision_is_resolved
    assert not branch_name.revision_is_resolved


def test_variable_input_and_model_specific_limits() -> None:
    config = campaign(names=("Chronos2Model",))
    assert config.input_chunk_length == (8, 24)
    with pytest.raises(ValidationError):
        FoundationCampaignConfig(
            **{
                **config.model_dump(),
                "input_chunk_length": (24, 8),
            }
        )
    with pytest.raises(ValidationError):
        FoundationCampaignConfig(
            **{
                **config.model_dump(),
                "output_chunk_length": 1025,
            }
        )


def test_tirex_requires_license_and_partial_finetuning_backend() -> None:
    with pytest.raises(ValidationError):
        FoundationModelConfig(
            public_name="TiRexModel",
            source=source("TiRexModel"),
        )
    with pytest.raises(ValidationError):
        FoundationModelConfig(
            public_name="TiRexModel",
            source=source("TiRexModel"),
            accept_license=True,
            finetuning=True,
        )
    partial = model(
        "TiRexModel",
        finetuning={"unfreeze": ["tirex.output*"]},
    )
    assert partial.model_args["tirex_kwargs"]["backend"] == "torch"


def test_source_certification_rejects_revision_and_manifest_drift() -> None:
    configured = source("Chronos2Model")
    mismatch = FoundationSourceObservation(
        source_kind="local",
        resolved_revision="c" * 40,
        local_dir_exists=True,
        local_manifest_sha256="b" * 64,
        files_count=1,
        total_bytes=1,
    )
    record = certify_source(configured, mismatch)
    assert record["failure_class"] == "FOUNDATION_REVISION_MISMATCH"
    missing_hash = mismatch.model_copy(
        update={
            "resolved_revision": configured.hub_model_revision,
            "local_manifest_sha256": None,
        }
    )
    record = certify_source(configured, missing_hash)
    assert record["failure_class"] == "FOUNDATION_ARTIFACT_UNVERIFIED"


def test_capability_drift_and_unsupported_covariates_fail_closed() -> None:
    drift = FakeTimesFM((8, 24), 3)
    drift.supports_future_covariates = True
    record = certify_capabilities(
        "TimesFM2p5Model",
        drift,
        use_past_covariates=False,
        use_future_covariates=False,
        series_layout="position_global_sequence",
    )
    assert record["failure_class"] == "CAPABILITY_DRIFT"
    clean = FakeTimesFM((8, 24), 3)
    record = certify_capabilities(
        "TimesFM2p5Model",
        clean,
        use_past_covariates=True,
        use_future_covariates=False,
        series_layout="position_global_sequence",
    )
    assert record["failure_class"] == "COVARIATE_UNSUPPORTED"


def test_zero_shot_and_finetuning_tracks_require_runtime_evidence() -> None:
    zero_bad = FoundationTrackObservation(
        enable_finetuning_effective=False,
        optimizer_steps=1,
        parameters_changed=True,
    )
    record = certify_track("zero_shot", zero_bad)
    assert record["failure_class"] == "ZERO_SHOT_TRAINING_DETECTED"
    fine_bad = FoundationTrackObservation(
        enable_finetuning_effective=True,
        optimizer_steps=0,
        parameters_changed=False,
    )
    record = certify_track("fine_tune", fine_bad)
    assert record["failure_class"] == "FINETUNING_NO_OPTIMIZER_STEP"


def test_package_import_failure_retains_all_requested_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import loto.darts_campaign.foundation_models as module

    def fail_import(name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(module.importlib, "import_module", fail_import)
    results = run_foundation_matrix(
        campaign(),
        frame(),
        geometry(),
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=zero_shot_probe,
        device_probe=gpu_probe,
    )
    assert len(results) == 4
    assert {item.failure_class for item in results} == {"DEPENDENCY_MISSING"}


def test_zero_shot_global_matrix_passes_with_evidence() -> None:
    original = frame()
    results = run_foundation_matrix(
        campaign(),
        original,
        geometry(),
        models_module=MODELS,
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=zero_shot_probe,
        device_probe=gpu_probe,
    )
    assert [item.status for item in results] == ["PASS"] * 4
    assert all(item.predictions is not None for item in results)
    assert all(item.source_certification["passed"] for item in results)
    assert all(item.capability_certification["passed"] for item in results)
    assert original.equals(frame())


def test_multivariate_and_position_local_shapes_are_certified() -> None:
    multi = run_foundation_matrix(
        campaign(
            names=("PatchTSTFMModel",),
            layout="position_multivariate",
        ),
        frame(),
        geometry(),
        models_module=MODELS,
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=zero_shot_probe,
        device_probe=gpu_probe,
    )[0]
    local = run_foundation_matrix(
        campaign(
            names=("TimesFM2p5Model",),
            layout="position_local",
        ),
        frame(),
        geometry(),
        models_module=MODELS,
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=zero_shot_probe,
        device_probe=gpu_probe,
    )[0]
    assert np.asarray(multi.predictions).shape == (3, 3)
    assert np.asarray(local.predictions).shape == (3, 3)
    assert len(local.device_certifications) == 3


def test_finetuning_track_uses_separate_evidence() -> None:
    config = campaign(
        names=("Chronos2Model",),
        track="fine_tune",
        finetuning={"unfreeze": ["encoder.*"]},
    )
    result = run_foundation_matrix(
        config,
        frame(),
        geometry(),
        models_module=MODELS,
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=fine_tune_probe,
        device_probe=gpu_probe,
    )[0]
    assert result.status == "PASS"
    assert result.track_certification["passed"]


def test_unresolved_revision_is_retained_without_instantiation() -> None:
    unresolved_model = FoundationModelConfig(
        public_name="Chronos2Model",
        source=source("Chronos2Model", "UNRESOLVED"),
    )
    config = FoundationCampaignConfig(
        run_id="unresolved",
        track="zero_shot",
        models=(unresolved_model,),
        input_chunk_length=8,
        output_chunk_length=1,
        series_layout="position_global_sequence",
        horizon=1,
        device={
            "requested_accelerator": "gpu",
            "devices": [0],
            "allow_cpu_fallback": False,
        },
    )
    result = run_foundation_matrix(
        config,
        frame(),
        geometry(),
        models_module=MODELS,
        timeseries_cls=FakeSeries,
        source_probe=source_probe,
        track_probe=zero_shot_probe,
        device_probe=gpu_probe,
    )[0]
    assert result.failure_class == "FOUNDATION_REVISION_UNRESOLVED"
