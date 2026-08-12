"""Versioned expanded implementation inventory.

Broad v1 remains frozen for the already-planned 174 x 6 runtime campaign.  This
module builds a parallel Expanded v2 inventory so framework umbrella entries can
be decomposed into source-backed executable implementations without silently
changing an active campaign denominator.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Literal

from loto.adapters.autogluon.inventory import SOURCE_ENSEMBLE_SPECS, SOURCE_MODEL_SPECS
from loto.models.catalog_full import ModelEntry, build_catalog

EXPANDED_INVENTORY_SCHEMA_VERSION = 2
AUTOGLOUON_BROAD_V1_ID = "autogluon-timeseries"

SourceKind = Literal[
    "broad_v1",
    "autogluon_source_model",
    "autogluon_source_ensemble",
]


@dataclass(frozen=True, slots=True)
class ImplementationIdentity:
    """One library-specific executable implementation identity.

    ``algorithm_id`` is intentionally separate from ``implementation_id``.  The
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


def expanded_implementation_catalog() -> tuple[ImplementationIdentity, ...]:
    """Return Expanded v2 while leaving the Broad v1 registry untouched."""

    broad_v1 = build_catalog()
    rows = [_from_broad_v1(entry) for entry in broad_v1 if entry.model_id != AUTOGLOUON_BROAD_V1_ID]
    rows.extend(autogluon_implementation_identities())
    _validate_identities(rows)
    return tuple(rows)


def expanded_inventory_counts() -> dict[str, Any]:
    """Return derived counts; no expanded total is hand-typed."""

    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    autogluon = autogluon_implementation_identities()
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
