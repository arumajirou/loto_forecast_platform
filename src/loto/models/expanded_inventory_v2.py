"""Authoritative composable Expanded-v2 inventory.

The legacy implementation_catalog remains a compatibility surface for the
already-merged AutoGluon/GluonTS phases. This module composes Darts Phase 2a on
top without changing Broad v1=174 or inferring runtime success from source
registration.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from loto.models import implementation_catalog as _base
from loto.models.catalog_full import build_catalog
from loto.models.darts_source_inventory import (
    DARTS_BROAD_V1_ID,
    DARTS_SOURCE_EXCLUSIONS,
    darts_source_identities,
    darts_source_manifest_sha256,
)

ImplementationIdentity = _base.ImplementationIdentity
AUTOGLOUON_BROAD_V1_ID = _base.AUTOGLOUON_BROAD_V1_ID
GLUONTS_BROAD_V1_ID = _base.GLUONTS_BROAD_V1_ID
EXPANDED_INVENTORY_SCHEMA_VERSION = _base.EXPANDED_INVENTORY_SCHEMA_VERSION


def darts_implementation_identities() -> tuple[ImplementationIdentity, ...]:
    """Return 55 fail-closed Darts 0.46.1 source implementation identities."""

    rows = [
        ImplementationIdentity(
            implementation_id=f"darts-{_base._slug(spec.public_name)}",
            algorithm_id=_base._algorithm_id(spec.public_name),
            library="darts",
            class_name=spec.public_name,
            family=spec.family,
            source_kind=cast(Any, "darts_public_forecaster"),
            execution_surface="darts_provider_pending",
            canonical_v1_model_id=DARTS_BROAD_V1_ID,
            source_alias=spec.public_name,
            capabilities=("source_declared",),
            notes=(
                "Darts 0.46.1 public forecasting source identity; "
                "capability classification, routing, and runtime certification are separate"
            ),
        )
        for spec in darts_source_identities()
    ]
    _base._validate_identities(rows)
    return tuple(rows)


def expanded_implementation_catalog() -> tuple[ImplementationIdentity, ...]:
    """Return current source-backed Expanded v2 with Darts Phase 2a included."""

    broad_v1 = build_catalog()
    replaced = {
        AUTOGLOUON_BROAD_V1_ID,
        GLUONTS_BROAD_V1_ID,
        DARTS_BROAD_V1_ID,
    }
    rows = [_base._from_broad_v1(entry) for entry in broad_v1 if entry.model_id not in replaced]
    rows.extend(_base.autogluon_implementation_identities())
    rows.extend(_base.gluonts_implementation_identities())
    rows.extend(darts_implementation_identities())
    _base._validate_identities(rows)
    return tuple(rows)


def expanded_inventory_counts() -> dict[str, Any]:
    """Return derived counts; hand-written totals are never authoritative."""

    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    autogluon = _base.autogluon_implementation_identities()
    gluonts = _base.gluonts_implementation_identities()
    darts = darts_implementation_identities()
    by_library = Counter(row.library for row in expanded)
    exclusions = Counter(row.kind for row in DARTS_SOURCE_EXCLUSIONS)
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
        "gluonts_registry_sha256": _base.gluonts_registry_sha256(),
        "darts_broad_v1_umbrella_count": sum(
            entry.model_id == DARTS_BROAD_V1_ID for entry in broad_v1
        ),
        "darts_public_exports": len(darts) + len(DARTS_SOURCE_EXCLUSIONS),
        "darts_excluded_abstract_bases": exclusions["ABSTRACT_BASE"],
        "darts_excluded_deprecated_aliases": exclusions["DEPRECATED_ALIAS"],
        "darts_expanded_total": len(darts),
        "darts_source_manifest_sha256": darts_source_manifest_sha256(),
        "by_library": dict(sorted(by_library.items())),
    }
