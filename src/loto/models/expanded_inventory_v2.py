"""Authoritative source-backed Expanded-v2 composition including Darts Phase 2a.

The current main implementation catalog remains the compatibility/base inventory.
This module replaces only the frozen Darts Broad-v1 umbrella with the pinned
Darts 0.46.1 source identities, preserving every expansion already present in
main (AutoGluon, GluonTS, skforecast, and future base additions).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from loto.models import implementation_catalog as _base
from loto.models.darts_source_inventory import (
    DARTS_BROAD_V1_ID,
    DARTS_SOURCE_EXCLUSIONS,
    DARTS_TARGET_VERSION,
    darts_source_identities,
    darts_source_manifest_sha256,
)

ImplementationIdentity = _base.ImplementationIdentity
EXPANDED_INVENTORY_SCHEMA_VERSION = _base.EXPANDED_INVENTORY_SCHEMA_VERSION + 1


def darts_implementation_identities() -> tuple[ImplementationIdentity, ...]:
    """Return 55 fail-closed Darts 0.46.1 source implementation identities."""

    manifest_sha256 = darts_source_manifest_sha256()
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
            source_declared=True,
            source_version=DARTS_TARGET_VERSION,
            source_revision=manifest_sha256,
            evidence_class="SOURCE_DECLARED",
            routability="UNKNOWN",
            runtime_status="NOT_RUN",
            runtime_certified=False,
            capabilities=("source_declared",),
            notes=(
                "Darts 0.46.1 public forecasting source identity; capability, game support, "
                "routing, construct/fit/predict, device and persistence certification are "
                "separate Phase 2b gates"
            ),
        )
        for spec in darts_source_identities()
    ]
    _base._validate_identities(rows)
    return tuple(rows)


def expanded_implementation_catalog() -> tuple[ImplementationIdentity, ...]:
    """Compose Darts Phase 2a on top of the current main Expanded inventory."""

    base_rows = list(_base.expanded_implementation_catalog())
    broad_darts_rows = [row for row in base_rows if row.implementation_id == DARTS_BROAD_V1_ID]
    if len(broad_darts_rows) != 1:
        raise AssertionError(
            "expected exactly one Darts Broad-v1 umbrella in base Expanded inventory; "
            f"observed={len(broad_darts_rows)}"
        )

    rows = [row for row in base_rows if row.implementation_id != DARTS_BROAD_V1_ID]
    rows.extend(darts_implementation_identities())
    _base._validate_identities(rows)
    return tuple(rows)


def expanded_inventory_counts() -> dict[str, Any]:
    """Return derived source-backed counts while preserving current base metadata."""

    base_counts = _base.expanded_inventory_counts()
    expanded = expanded_implementation_catalog()
    darts = darts_implementation_identities()
    by_library = Counter(row.library for row in expanded)
    exclusions = Counter(row.kind for row in DARTS_SOURCE_EXCLUSIONS)

    counts = dict(base_counts)
    counts.update(
        {
            "schema_version": EXPANDED_INVENTORY_SCHEMA_VERSION,
            "base_expanded_v2": base_counts["expanded_v2"],
            "expanded_v2": len(expanded),
            "delta_vs_broad_v1": len(expanded) - base_counts["broad_v1"],
            "darts_broad_v1_umbrella_count": 1,
            "darts_public_exports": len(darts) + len(DARTS_SOURCE_EXCLUSIONS),
            "darts_excluded_abstract_bases": exclusions["ABSTRACT_BASE"],
            "darts_excluded_deprecated_aliases": exclusions["DEPRECATED_ALIAS"],
            "darts_expanded_total": len(darts),
            "darts_source_manifest_sha256": darts_source_manifest_sha256(),
            "by_library": dict(sorted(by_library.items())),
        }
    )
    return counts


__all__ = [
    "EXPANDED_INVENTORY_SCHEMA_VERSION",
    "ImplementationIdentity",
    "darts_implementation_identities",
    "expanded_implementation_catalog",
    "expanded_inventory_counts",
]
