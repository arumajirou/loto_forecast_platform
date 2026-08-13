"""Versioned expanded implementation inventory.

Broad v1 remains frozen for the already-planned 174 x 6 runtime campaign. This
module builds a parallel Expanded v2 inventory so framework umbrella entries can
be decomposed into source-backed executable implementations without silently
changing an active campaign denominator.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Literal

from loto.adapters.autogluon.inventory import SOURCE_ENSEMBLE_SPECS, SOURCE_MODEL_SPECS
from loto.adapters.gluonts.p6_registry import (
    model_specs as gluonts_model_specs,
    registry_payload as gluonts_registry_payload,
    registry_sha256 as gluonts_registry_sha256,
)
from loto.models.catalog_full import ModelEntry, build_catalog
from loto.models.skforecast_inventory import (
    SKFORECAST_IMPLEMENTATION_SPECS,
    SKFORECAST_OPERATOR_EVIDENCE_REVISION,
    SKFORECAST_SOURCE_REVISION,
    SKFORECAST_VERSION,
)

EXPANDED_INVENTORY_SCHEMA_VERSION = 3
AUTOGLOUON_BROAD_V1_ID = "autogluon-timeseries"
GLUONTS_BROAD_V1_ID = "gluonts-deepar"
SKFORECAST_BROAD_V1_ID = "skforecast-recursive"

SourceKind = Literal[
    "broad_v1",
    "autogluon_source_model",
    "autogluon_source_ensemble",
    "gluonts_p6_registry",
    "skforecast_strategy",
]


@dataclass(frozen=True, slots=True)
class ImplementationIdentity:
    """One library-specific executable implementation identity."""

    implementation_id: str
    algorithm_id: str
    library: str
    class_name: str
    family: str
    source_kind: SourceKind
    execution_surface: str
    canonical_v1_model_id: str | None = None
    source_alias: str | None = None
    source_declared: bool = True
    source_version: str | None = None
    source_revision: str | None = None
    evidence_class: str = "SOURCE_DECLARED"
    evidence_revision: str | None = None
    routability: str = "UNKNOWN"
    runtime_status: str = "NOT_RUN"
    runtime_certified: bool = False
    block_reason: str | None = None
    capabilities: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slug(value: str) -> str:
    chars: list[str] = []
    previous_dash = False
    for char in value.strip():
        if char.isalnum():
            chars.append(char.lower())
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-")


_ALGORITHM_ALIASES = {
    "temporalfusiontransformer": "tft",
    "autoarima": "autoarima",
    "autoets": "autoets",
    "autoces": "autoces",
    "deepar": "deepar",
    "dlinear": "dlinear",
    "patchtst": "patchtst",
    "tide": "tide",
    "chronos2": "chronos-2",
}

_GLUONTS_FAMILIES = {
    "DeepNPTSEstimator": "deep_probabilistic",
    "DeepAREstimator": "deep_probabilistic",
    "TiDEEstimator": "mlp",
    "SimpleFeedForwardEstimator": "mlp",
    "TemporalFusionTransformerEstimator": "transformer",
    "WaveNetEstimator": "cnn",
    "DLinearEstimator": "linear",
    "PatchTSTEstimator": "transformer",
    "LagTSTEstimator": "transformer",
}


def _algorithm_id(name: str) -> str:
    compact = "".join(char.lower() for char in name if char.isalnum())
    return _ALGORITHM_ALIASES.get(compact, _slug(name))


def _from_broad_v1(entry: ModelEntry) -> ImplementationIdentity:
    return ImplementationIdentity(
        implementation_id=entry.model_id,
        algorithm_id=_algorithm_id(entry.class_name),
        library=entry.library,
        class_name=entry.class_name,
        family=entry.family,
        source_kind="broad_v1",
        execution_surface="broad_v1",
        canonical_v1_model_id=entry.model_id,
        capabilities=entry.capabilities,
        notes=entry.notes,
    )


def autogluon_implementation_identities() -> tuple[ImplementationIdentity, ...]:
    """Expand the repository's source-declared AutoGluon inventory."""

    rows: list[ImplementationIdentity] = []
    for spec in SOURCE_MODEL_SPECS:
        rows.append(
            ImplementationIdentity(
                implementation_id=f"autogluon-{_slug(spec.alias)}",
                algorithm_id=_algorithm_id(spec.alias),
                library="autogluon",
                class_name=spec.class_name,
                family=spec.category,
                source_kind="autogluon_source_model",
                execution_surface="provider",
                canonical_v1_model_id=AUTOGLOUON_BROAD_V1_ID,
                source_alias=spec.alias,
                capabilities=("position_series", "automl_provider"),
                notes="source-declared AutoGluon model; runtime certification is separate",
            )
        )

    ensemble_specs: dict[str, list[Any]] = defaultdict(list)
    for spec in SOURCE_ENSEMBLE_SPECS:
        ensemble_specs[spec.expected_class_name].append(spec)

    for class_name, specs in ensemble_specs.items():
        canonical = next((spec for spec in specs if spec.alias_of is None), specs[0])
        aliases = tuple(spec.selectable_name for spec in specs)
        rows.append(
            ImplementationIdentity(
                implementation_id=f"autogluon-ensemble-{_slug(canonical.selectable_name)}",
                algorithm_id=_algorithm_id(class_name),
                library="autogluon",
                class_name=class_name,
                family="ensemble",
                source_kind="autogluon_source_ensemble",
                execution_surface="provider",
                canonical_v1_model_id=AUTOGLOUON_BROAD_V1_ID,
                source_alias=canonical.selectable_name,
                capabilities=("position_series", "ensemble", "automl_provider"),
                notes=(
                    "source-declared AutoGluon ensemble; selectable aliases="
                    + ",".join(aliases)
                    + "; runtime certification is separate"
                ),
            )
        )

    _validate_identities(rows)
    return tuple(rows)


def gluonts_implementation_identities() -> tuple[ImplementationIdentity, ...]:
    """Expand the GluonTS Broad identity from the deterministic P6 registry."""

    payload = gluonts_registry_payload()
    source_tags = ",".join(payload["official_source_tags"])
    rows: list[ImplementationIdentity] = []

    for spec in gluonts_model_specs():
        model_name = spec.model_class.removesuffix("Estimator")
        capabilities = [
            "position_series",
            "fit",
            "predict",
            "save_reload_contract",
            "cpu_p6_contract",
            f"distribution_{spec.distribution_mode.value.lower()}",
            f"trainer_{spec.trainer_kind.value.lower()}",
        ]
        if spec.supports_context_length:
            capabilities.append("context_length")

        rows.append(
            ImplementationIdentity(
                implementation_id=f"gluonts-torch-{_slug(model_name)}",
                algorithm_id=_algorithm_id(model_name),
                library="gluonts",
                class_name=spec.model_class,
                family=_GLUONTS_FAMILIES[spec.model_class],
                source_kind="gluonts_p6_registry",
                execution_surface="gluonts_p6_provider",
                canonical_v1_model_id=GLUONTS_BROAD_V1_ID,
                source_alias=spec.module_path,
                capabilities=tuple(capabilities),
                notes=(
                    f"source_path={spec.source_path}; official_source_tags={source_tags}; "
                    "P6 device policy=cpu; exogenous/multivariate/GPU support is not "
                    "certified by this inventory; runtime certification is separate"
                ),
            )
        )

    _validate_identities(rows)
    return tuple(rows)


def skforecast_implementation_identities() -> tuple[ImplementationIdentity, ...]:
    """Return the pinned reviewed skforecast 0.23.0 Phase 4A manifest."""

    rows = [
        ImplementationIdentity(
            implementation_id=spec.implementation_id,
            algorithm_id=spec.algorithm_id,
            library="skforecast",
            class_name=spec.class_name,
            family=spec.family,
            source_kind="skforecast_strategy",
            execution_surface="expanded_inventory",
            canonical_v1_model_id=SKFORECAST_BROAD_V1_ID,
            source_alias=spec.source_alias,
            source_declared=spec.source_declared,
            source_version=SKFORECAST_VERSION,
            source_revision=SKFORECAST_SOURCE_REVISION,
            evidence_class=spec.evidence_class,
            evidence_revision=spec.evidence_revision,
            routability=spec.routability,
            runtime_status=spec.runtime_status,
            runtime_certified=False,
            block_reason=spec.block_reason,
            capabilities=spec.capabilities,
            notes=spec.notes,
        )
        for spec in SKFORECAST_IMPLEMENTATION_SPECS
    ]
    _validate_identities(rows)
    return tuple(rows)


def expanded_implementation_catalog() -> tuple[ImplementationIdentity, ...]:
    """Return current Expanded v2 while leaving Broad v1 untouched."""

    broad_v1 = build_catalog()
    replaced_broad_ids = {
        AUTOGLOUON_BROAD_V1_ID,
        GLUONTS_BROAD_V1_ID,
        SKFORECAST_BROAD_V1_ID,
    }
    rows = [
        _from_broad_v1(entry)
        for entry in broad_v1
        if entry.model_id not in replaced_broad_ids
    ]
    rows.extend(autogluon_implementation_identities())
    rows.extend(gluonts_implementation_identities())
    rows.extend(skforecast_implementation_identities())
    _validate_identities(rows)
    return tuple(rows)


def expanded_inventory_counts() -> dict[str, Any]:
    """Return derived counts; no expanded total is hand-typed."""

    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    autogluon = autogluon_implementation_identities()
    gluonts = gluonts_implementation_identities()
    skforecast = skforecast_implementation_identities()
    by_library = Counter(row.library for row in expanded)
    return {
        "schema_version": EXPANDED_INVENTORY_SCHEMA_VERSION,
        "broad_v1": len(broad_v1),
        "expanded_v2": len(expanded),
        "delta_vs_broad_v1": len(expanded) - len(broad_v1),
        "autogluon_broad_v1_umbrella_count": sum(
            entry.model_id == AUTOGLOUON_BROAD_V1_ID for entry in broad_v1
        ),
        "autogluon_source_models": sum(
            row.source_kind == "autogluon_source_model" for row in autogluon
        ),
        "autogluon_unique_ensembles": sum(
            row.source_kind == "autogluon_source_ensemble" for row in autogluon
        ),
        "autogluon_expanded_total": len(autogluon),
        "gluonts_broad_v1_umbrella_count": sum(
            entry.model_id == GLUONTS_BROAD_V1_ID for entry in broad_v1
        ),
        "gluonts_p6_source_models": len(gluonts),
        "gluonts_expanded_total": len(gluonts),
        "gluonts_registry_sha256": gluonts_registry_sha256(),
        "skforecast_broad_v1_umbrella_count": sum(
            entry.model_id == SKFORECAST_BROAD_V1_ID for entry in broad_v1
        ),
        "skforecast_expanded_total": len(skforecast),
        "skforecast_evidence_class": dict(
            sorted(Counter(row.evidence_class for row in skforecast).items())
        ),
        "skforecast_runtime_status": dict(
            sorted(Counter(row.runtime_status for row in skforecast).items())
        ),
        "by_library": dict(sorted(by_library.items())),
    }


def _validate_identities(rows: list[ImplementationIdentity]) -> None:
    ids = [row.implementation_id for row in rows]
    duplicates = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise AssertionError(f"duplicate Expanded v2 implementation IDs: {duplicates}")
    if any(not row.algorithm_id for row in rows):
        raise AssertionError("Expanded v2 algorithm_id must not be empty")
    if any(row.runtime_certified and row.runtime_status != "PASS" for row in rows):
        raise AssertionError("runtime_certified requires runtime_status=PASS")
    if any(row.runtime_certified and row.evidence_class != "REPOSITORY_RETAINED" for row in rows):
        raise AssertionError("runtime_certified requires repository-retained evidence")


__all__ = [
    "AUTOGLOUON_BROAD_V1_ID",
    "EXPANDED_INVENTORY_SCHEMA_VERSION",
    "GLUONTS_BROAD_V1_ID",
    "ImplementationIdentity",
    "SKFORECAST_BROAD_V1_ID",
    "SKFORECAST_OPERATOR_EVIDENCE_REVISION",
    "SKFORECAST_SOURCE_REVISION",
    "SKFORECAST_VERSION",
    "autogluon_implementation_identities",
    "expanded_implementation_catalog",
    "expanded_inventory_counts",
    "gluonts_implementation_identities",
    "skforecast_implementation_identities",
]
