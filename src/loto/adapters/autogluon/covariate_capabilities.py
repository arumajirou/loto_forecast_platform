from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable

from .inventory import SOURCE_MODEL_SPECS, TARGET_AUTOGLUON_VERSION


class CovariateRole(StrEnum):
    KNOWN = "known_covariates"
    PAST = "past_covariates"
    STATIC = "static_features"


class CovariateCapabilityError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        model_id: str | None = None,
        role: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.model_id = model_id
        self.role = role


@dataclass(frozen=True, slots=True)
class ModelCovariateCapability:
    model_id: str
    native_known: bool = False
    native_past: bool = False
    native_static: bool = False
    evidence: str = "AutoGluon 1.5.0 model-zoo summary table"

    def supports_native(self, role: CovariateRole) -> bool:
        return {
            CovariateRole.KNOWN: self.native_known,
            CovariateRole.PAST: self.native_past,
            CovariateRole.STATIC: self.native_static,
        }[role]


@dataclass(frozen=True, slots=True)
class ModelRoleDecision:
    model_id: str
    role: str
    route: str
    covariate_regressor: str | None


@dataclass(frozen=True, slots=True)
class CovariateCapabilityDecision:
    schema_version: int
    autogluon_version: str
    execution_mode: str
    selected_model_ids: tuple[str, ...]
    requested_roles: tuple[str, ...]
    model_roles: tuple[ModelRoleDecision, ...]
    decision_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_model_ids"] = list(self.selected_model_ids)
        payload["requested_roles"] = list(self.requested_roles)
        payload["model_roles"] = [asdict(value) for value in self.model_roles]
        return payload


_NATIVE = {
    "DirectTabular": (True, False, True),
    "PerStepTabular": (True, False, True),
    "RecursiveTabular": (True, False, True),
    "DeepAR": (True, False, True),
    "PatchTST": (True, False, False),
    "TemporalFusionTransformer": (True, True, True),
    "TiDE": (True, False, True),
    "WaveNet": (True, False, True),
    "Chronos2": (True, True, False),
}

_ALLOWED_REGRESSORS = frozenset({"LR", "GBM", "CAT", "XGB", "RF"})


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def model_capability_inventory() -> tuple[ModelCovariateCapability, ...]:
    result: list[ModelCovariateCapability] = []
    for spec in SOURCE_MODEL_SPECS:
        known, past, static = _NATIVE.get(spec.alias, (False, False, False))
        evidence = "AutoGluon 1.5.0 model-zoo summary table"
        if spec.alias == "PerStepTabular":
            evidence = "AutoGluon 1.5.0 AbstractMLForecastModel source capability flags"
        result.append(
            ModelCovariateCapability(
                model_id=spec.alias,
                native_known=known,
                native_past=past,
                native_static=static,
                evidence=evidence,
            )
        )
    return tuple(result)


def validate_inventory_coverage() -> None:
    source = {spec.alias for spec in SOURCE_MODEL_SPECS}
    capability = {item.model_id for item in model_capability_inventory()}
    if source != capability:
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_INVENTORY_MISMATCH",
            f"source/capability inventory mismatch missing={sorted(source-capability)} "
            f"unexpected={sorted(capability-source)}",
        )


def requested_roles(
    *,
    known_covariate_names: Iterable[str],
    past_covariate_names: Iterable[str],
    static_feature_names: Iterable[str],
) -> tuple[CovariateRole, ...]:
    roles: list[CovariateRole] = []
    if tuple(known_covariate_names):
        roles.append(CovariateRole.KNOWN)
    if tuple(past_covariate_names):
        roles.append(CovariateRole.PAST)
    if tuple(static_feature_names):
        roles.append(CovariateRole.STATIC)
    return tuple(roles)


def _regressor(config: dict[str, Any], *, model_id: str) -> str | None:
    value = config.get("covariate_regressor")
    if value is None:
        return None
    if not isinstance(value, str) or value not in _ALLOWED_REGRESSORS:
        raise CovariateCapabilityError(
            "COVARIATE_REGRESSOR_INVALID",
            f"model {model_id!r} covariate_regressor must be one of "
            f"{sorted(_ALLOWED_REGRESSORS)} or null",
            model_id=model_id,
        )
    return value


def _native_enabled(
    capability: ModelCovariateCapability,
    role: CovariateRole,
    config: dict[str, Any],
) -> bool:
    if not capability.supports_native(role):
        return False
    disable_key = {
        CovariateRole.KNOWN: "disable_known_covariates",
        CovariateRole.PAST: "disable_past_covariates",
        CovariateRole.STATIC: "disable_static_features",
    }[role]
    return config.get(disable_key) is not True


def build_covariate_capability_decision(
    *,
    execution_mode: str,
    selected_model_ids: Iterable[str],
    model_hyperparameters: dict[str, Any],
    roles: Iterable[CovariateRole],
) -> CovariateCapabilityDecision:
    validate_inventory_coverage()
    selected = tuple(str(value) for value in selected_model_ids)
    requested = tuple(roles)
    if not requested:
        raise CovariateCapabilityError(
            "COVARIATE_ROLE_REQUIRED",
            "at least one covariate role is required for capability validation",
        )
    if execution_mode == "preset_automl" or not selected:
        raise CovariateCapabilityError(
            "COVARIATES_REQUIRE_EXPLICIT_MODELS",
            "formal covariate execution requires explicit model_ids; preset AutoML may mix "
            "models that consume and ignore the requested features",
        )

    inventory = {item.model_id: item for item in model_capability_inventory()}
    unknown = sorted(set(selected) - set(inventory))
    if unknown:
        raise CovariateCapabilityError(
            "UNKNOWN_MODEL_ID",
            f"covariate capability inventory has no model IDs: {unknown}",
        )
    if set(model_hyperparameters) != set(selected):
        raise CovariateCapabilityError(
            "COVARIATE_MODEL_CONFIG_MISMATCH",
            "effective hyperparameter model keys must exactly match selected_model_ids",
        )

    decisions: list[ModelRoleDecision] = []
    for model_id in selected:
        config = model_hyperparameters[model_id]
        if not isinstance(config, dict):
            raise CovariateCapabilityError(
                "COVARIATE_MODEL_CONFIG_INVALID",
                f"effective hyperparameters for model {model_id!r} must be a dictionary",
                model_id=model_id,
            )
        regressor = _regressor(config, model_id=model_id)
        capability = inventory[model_id]
        for role in requested:
            if _native_enabled(capability, role, config):
                route = "native"
            elif role in {CovariateRole.KNOWN, CovariateRole.STATIC} and regressor is not None:
                route = "covariate_regressor"
            else:
                raise CovariateCapabilityError(
                    "MODEL_COVARIATE_ROLE_UNSUPPORTED",
                    f"model {model_id!r} cannot consume requested role {role.value!r} "
                    "under the effective hyperparameters",
                    model_id=model_id,
                    role=role.value,
                )
            decisions.append(
                ModelRoleDecision(
                    model_id=model_id,
                    role=role.value,
                    route=route,
                    covariate_regressor=regressor,
                )
            )

    payload_without_hash = {
        "schema_version": 1,
        "autogluon_version": TARGET_AUTOGLUON_VERSION,
        "execution_mode": execution_mode,
        "selected_model_ids": list(selected),
        "requested_roles": [role.value for role in requested],
        "model_roles": [asdict(value) for value in decisions],
    }
    return CovariateCapabilityDecision(
        schema_version=1,
        autogluon_version=TARGET_AUTOGLUON_VERSION,
        execution_mode=execution_mode,
        selected_model_ids=selected,
        requested_roles=tuple(role.value for role in requested),
        model_roles=tuple(decisions),
        decision_sha256=_canonical_sha256(payload_without_hash),
    )
