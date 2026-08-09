from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPECTED_ESTIMATORS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)


class TrainingApi(StrEnum):
    LIGHTNING = "LIGHTNING"
    DEEP_NPTS_EPOCHS = "DEEP_NPTS_EPOCHS"


class ConstructorState(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class FormalState(StrEnum):
    EXECUTION_PENDING = "EXECUTION_PENDING"
    DISCOVERED_ONLY = "DISCOVERED_ONLY"
    CONSTRUCTED_ONLY = "CONSTRUCTED_ONLY"
    FAILED = "FAILED"


class EstimatorProfile(BaseModel):
    """Version-independent minimal constructor contract for one GluonTS Estimator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    module: str
    training_api: TrainingApi
    required_fields: tuple[str, ...]
    smoke_defaults: dict[str, Any]
    explicit_distribution_outputs: tuple[str, ...] = ()
    supports_default_distribution: bool = True
    notes: str = ""

    @model_validator(mode="after")
    def validate_profile(self) -> EstimatorProfile:
        if self.training_api is TrainingApi.DEEP_NPTS_EPOCHS:
            if "epochs" not in self.smoke_defaults:
                raise ValueError("DeepNPTS profile requires epochs")
            if "trainer_kwargs" in self.smoke_defaults:
                raise ValueError("DeepNPTS profile cannot use trainer_kwargs")
        elif "trainer_kwargs" not in self.smoke_defaults:
            raise ValueError("Lightning profiles require trainer_kwargs")
        if set(self.required_fields) & set(self.smoke_defaults):
            raise ValueError("required fields and smoke defaults must not overlap")
        return self


PROFILES = (
    EstimatorProfile(
        name="DeepNPTSEstimator",
        module="gluonts.torch.model.deep_npts",
        training_api=TrainingApi.DEEP_NPTS_EPOCHS,
        required_fields=("freq", "prediction_length", "context_length"),
        smoke_defaults={"batch_size": 4, "num_batches_per_epoch": 1, "epochs": 1},
        supports_default_distribution=False,
        notes="Uses epochs instead of Lightning trainer_kwargs.",
    ),
    EstimatorProfile(
        name="DeepAREstimator",
        module="gluonts.torch.model.deepar",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("freq", "prediction_length", "context_length"),
        smoke_defaults={
            "num_layers": 1,
            "hidden_size": 4,
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "num_parallel_samples": 4,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("StudentTOutput", "ImplicitQuantileNetworkOutput"),
    ),
    EstimatorProfile(
        name="TiDEEstimator",
        module="gluonts.torch.model.tide",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("freq", "prediction_length"),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("QuantileOutput",),
    ),
    EstimatorProfile(
        name="SimpleFeedForwardEstimator",
        module="gluonts.torch.model.simple_feedforward",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("prediction_length",),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("QuantileOutput",),
    ),
    EstimatorProfile(
        name="TemporalFusionTransformerEstimator",
        module="gluonts.torch.model.tft",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("freq", "prediction_length"),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("StudentTOutput",),
    ),
    EstimatorProfile(
        name="WaveNetEstimator",
        module="gluonts.torch.model.wavenet",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("freq", "prediction_length"),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
    ),
    EstimatorProfile(
        name="DLinearEstimator",
        module="gluonts.torch.model.d_linear",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("prediction_length",),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("QuantileOutput",),
    ),
    EstimatorProfile(
        name="PatchTSTEstimator",
        module="gluonts.torch.model.patch_tst",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("prediction_length",),
        smoke_defaults={
            "patch_len": 16,
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
        explicit_distribution_outputs=("QuantileOutput",),
    ),
    EstimatorProfile(
        name="LagTSTEstimator",
        module="gluonts.torch.model.lag_tst",
        training_api=TrainingApi.LIGHTNING,
        required_fields=("freq", "prediction_length"),
        smoke_defaults={
            "batch_size": 4,
            "num_batches_per_epoch": 1,
            "trainer_kwargs": {"max_epochs": 1, "accelerator": "cpu", "devices": 1},
        },
    ),
)

PROFILE_BY_NAME = {profile.name: profile for profile in PROFILES}


class ConstructorEvidence(BaseModel):
    """Fail-closed discovery and optional construction evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_name: str
    module: str
    lane: Literal["compat", "latest"]
    import_state: ConstructorState = ConstructorState.NOT_RUN
    export_state: ConstructorState = ConstructorState.NOT_RUN
    signature_state: ConstructorState = ConstructorState.NOT_RUN
    constructor_state: ConstructorState = ConstructorState.NOT_RUN
    constructor_signature: str | None = None
    planned_kwargs: dict[str, Any] = Field(default_factory=dict)
    rejected_arguments: dict[str, str] = Field(default_factory=dict)
    formal_state: FormalState = FormalState.EXECUTION_PENDING
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> ConstructorEvidence:
        if self.formal_state is FormalState.FAILED and not self.errors:
            raise ValueError("FAILED evidence requires errors")
        if self.formal_state is FormalState.CONSTRUCTED_ONLY:
            required = (
                self.import_state,
                self.export_state,
                self.signature_state,
                self.constructor_state,
            )
            if any(state is not ConstructorState.PASS for state in required):
                raise ValueError("CONSTRUCTED_ONLY requires all constructor checks to PASS")
            if self.errors or self.rejected_arguments:
                raise ValueError("CONSTRUCTED_ONLY cannot contain errors or rejected arguments")
        return self


class P6ConstructorMatrix(BaseModel):
    """Nine-estimator constructor matrix produced by one isolated lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    construct_requested: bool
    runtime_versions: dict[str, str | None] = Field(default_factory=dict)
    entries: list[ConstructorEvidence]
    summary: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_matrix(self) -> P6ConstructorMatrix:
        names = [entry.model_name for entry in self.entries]
        if names != list(EXPECTED_ESTIMATORS):
            raise ValueError("P6 matrix must contain all nine estimators in canonical order")
        computed = {state.value: 0 for state in FormalState}
        for entry in self.entries:
            computed[entry.formal_state.value] += 1
        if self.summary and self.summary != computed:
            raise ValueError("P6 matrix summary does not match entries")
        object.__setattr__(self, "summary", computed)
        return self


def validate_registry() -> None:
    names = tuple(profile.name for profile in PROFILES)
    if names != EXPECTED_ESTIMATORS:
        raise ValueError("P6 profile registry does not match expected estimator inventory")
    if len(PROFILE_BY_NAME) != len(PROFILES):
        raise ValueError("P6 profile registry contains duplicate estimator names")


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def matrix_sha256(matrix: P6ConstructorMatrix) -> str:
    return hashlib.sha256(canonical_json_bytes(matrix.model_dump(mode="json"))).hexdigest()


def constructor_kwargs(
    profile: EstimatorProfile,
    *,
    freq: str = "D",
    prediction_length: int = 1,
    context_length: int = 32,
    model_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = {
        "freq": freq,
        "prediction_length": prediction_length,
        "context_length": context_length,
    }
    planned = {name: values[name] for name in profile.required_fields}
    planned.update(profile.smoke_defaults)
    planned.update(model_arguments or {})
    return planned


def _distribution_instance(name: str) -> Any:
    module = importlib.import_module("gluonts.torch.distributions")
    cls = getattr(module, name)
    if name == "QuantileOutput":
        return cls(quantiles=[0.1, 0.5, 0.9])
    return cls()


def inspect_estimator(
    profile: EstimatorProfile,
    lane: Literal["compat", "latest"],
    *,
    construct: bool = False,
    freq: str = "D",
    prediction_length: int = 1,
    context_length: int = 32,
    model_arguments: dict[str, Any] | None = None,
    distribution_output: str | None = None,
    importer: Callable[[str], Any] = importlib.import_module,
) -> ConstructorEvidence:
    planned = constructor_kwargs(
        profile,
        freq=freq,
        prediction_length=prediction_length,
        context_length=context_length,
        model_arguments=model_arguments,
    )
    rejected: dict[str, str] = {}
    if distribution_output is not None:
        if distribution_output not in profile.explicit_distribution_outputs:
            rejected["distribution_output"] = (
                f"{distribution_output} is not certified for {profile.name}"
            )
        else:
            planned["distr_output"] = distribution_output
    try:
        module = importer(profile.module)
    except Exception as exc:
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.BLOCKED,
            planned_kwargs=planned,
            rejected_arguments=rejected,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    value = getattr(module, profile.name, None)
    if not inspect.isclass(value):
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.PASS,
            export_state=ConstructorState.FAIL,
            planned_kwargs=planned,
            rejected_arguments=rejected,
            formal_state=FormalState.FAILED,
            errors=[f"{profile.module}.{profile.name} is not an exported class"],
        )
    try:
        signature = inspect.signature(value)
    except Exception as exc:
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.PASS,
            export_state=ConstructorState.PASS,
            signature_state=ConstructorState.FAIL,
            planned_kwargs=planned,
            rejected_arguments=rejected,
            formal_state=FormalState.FAILED,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    for name in planned:
        if name not in signature.parameters and not accepts_kwargs:
            rejected[name] = "constructor signature does not accept this argument"
    if rejected:
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.PASS,
            export_state=ConstructorState.PASS,
            signature_state=ConstructorState.PASS,
            constructor_signature=str(signature),
            planned_kwargs=planned,
            rejected_arguments=rejected,
            formal_state=FormalState.FAILED,
            errors=["one or more requested constructor arguments were rejected"],
        )
    if not construct:
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.PASS,
            export_state=ConstructorState.PASS,
            signature_state=ConstructorState.PASS,
            constructor_signature=str(signature),
            planned_kwargs=planned,
            formal_state=FormalState.DISCOVERED_ONLY,
        )
    actual = dict(planned)
    if distribution_output is not None:
        try:
            actual["distr_output"] = _distribution_instance(distribution_output)
        except Exception as exc:
            return ConstructorEvidence(
                model_name=profile.name,
                module=profile.module,
                lane=lane,
                import_state=ConstructorState.PASS,
                export_state=ConstructorState.PASS,
                signature_state=ConstructorState.PASS,
                constructor_state=ConstructorState.FAIL,
                constructor_signature=str(signature),
                planned_kwargs=planned,
                formal_state=FormalState.FAILED,
                errors=[f"distribution construction failed: {type(exc).__name__}: {exc}"],
            )
    try:
        value(**actual)
    except Exception as exc:
        return ConstructorEvidence(
            model_name=profile.name,
            module=profile.module,
            lane=lane,
            import_state=ConstructorState.PASS,
            export_state=ConstructorState.PASS,
            signature_state=ConstructorState.PASS,
            constructor_state=ConstructorState.FAIL,
            constructor_signature=str(signature),
            planned_kwargs=planned,
            rejected_arguments=rejected,
            formal_state=FormalState.FAILED,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    return ConstructorEvidence(
        model_name=profile.name,
        module=profile.module,
        lane=lane,
        import_state=ConstructorState.PASS,
        export_state=ConstructorState.PASS,
        signature_state=ConstructorState.PASS,
        constructor_state=ConstructorState.PASS,
        constructor_signature=str(signature),
        planned_kwargs=planned,
        formal_state=FormalState.CONSTRUCTED_ONLY,
    )


def build_matrix(
    lane: Literal["compat", "latest"],
    *,
    construct: bool = False,
    runtime_versions: dict[str, str | None] | None = None,
    importer: Callable[[str], Any] = importlib.import_module,
) -> P6ConstructorMatrix:
    validate_registry()
    entries = [
        inspect_estimator(profile, lane, construct=construct, importer=importer)
        for profile in PROFILES
    ]
    return P6ConstructorMatrix(
        lane=lane,
        construct_requested=construct,
        runtime_versions=runtime_versions or {},
        entries=entries,
    )
