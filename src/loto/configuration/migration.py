"""Explicit migration registry for strict configuration schemas.

The loader never migrates implicitly. A future migration must be registered, tested, and invoked
explicitly before normal validation.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .contracts import CONFIG_SCHEMA_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]
MIGRATIONS: dict[tuple[str, str], Migration] = {}


class ConfigMigrationRequiredError(ValueError):
    """Raised when an input cannot be validated without an explicit migration."""


def source_schema_version(payload: dict[str, Any]) -> str:
    value = payload.get("config_schema_version")
    if not isinstance(value, str) or not value.strip():
        raise ConfigMigrationRequiredError(
            "config_schema_version is required; legacy unversioned configs need explicit migration"
        )
    return value


def migrate_payload(
    payload: dict[str, Any],
    *,
    target_version: str = CONFIG_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return a migrated copy or fail when no reviewed migration is registered."""

    current = source_schema_version(payload)
    migrated = deepcopy(payload)
    if current == target_version:
        return migrated
    migration = MIGRATIONS.get((current, target_version))
    if migration is None:
        raise ConfigMigrationRequiredError(
            f"no reviewed config migration registered: {current} -> {target_version}"
        )
    result = migration(migrated)
    if result.get("config_schema_version") != target_version:
        raise ConfigMigrationRequiredError("migration did not produce the requested schema version")
    return result
