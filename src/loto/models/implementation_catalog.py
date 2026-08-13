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

EXPANDED_INVENTORY_SCHEMA_VERSION = 2
AUTOGLOUON_BROAD_V1_ID = "autogluon-timeseries"
GLUONTS_BROAD_V1_ID = "gluonts-deepar"

SourceKind = Literal[
    "broad_v1",
    "autogluon_source_model",
    "autogluon_source_ensemble",
    "gluonts_p6_registry",
]


@dataclass(frozen=True, slots=True)
class ImplementationIdentity:
    """One library-specific executable implementation identity.

    ``algorithm_id`` is intentionally separate from ``implementation_id``. The
    former can be shared by equivalent scientific algorithms implemented by
    different libraries, while the latter is always library/runtime specific.
    """

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
    runtime_status: str = "NOT_RUN"
    runtime_certified: bool = False
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
    """Expand the repository's source-declared AutoGluon inventory.

    AutoGluon currently has one Broad v1 umbrella entry, but the pinned source
    inventory declares individual model aliases and ensemble implementations.
    Selectable ensemble aliases resolving to the same class are counted once.
    """

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
    """Expand the frozen GluonTS Broad identity from the deterministic P6 registry.

    The P6 registry is source-backed and deterministic, but its source declaration
    must remain separate from runtime certification. The current P6 contract is
    deliberately CPU-pinned; GPU, exogenous and multivariate behavior are not
    inferred from registration alone.
    """

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


def expanded_implementation_catalog() -> tuple[ImplementationIdentity, ...]:
    """Return current Expanded v2 while leaving the Broad v1 registry untouched."""

    broad_v1 = build_catalog()
    replaced_broad_ids = {AUTOGLOUON_BROAD_V1_ID, GLUONTS_BROAD_V1_ID}
    rows = [
        _from_broad_v1(entry)
        for entry in broad_v1
        if entry.model_id not in replaced_broad_ids
    ]
    rows.extend(autogluon_implementation_identities())
    rows.extend(gluonts_implementation_identities())
    _validate_identities(rows)
    return tuple(rows)


def expanded_inventory_counts() -> dict[str, Any]:
    """Return derived counts; no expanded total is hand-typed."""

    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    autogluon = autogluon_implementation_identities()
    gluonts = gluonts_implementation_identities()
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
