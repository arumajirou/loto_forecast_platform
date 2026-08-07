# Strict Configuration Migration Guide

## Principle

Configuration migration is explicit, version-to-version, test-backed, and never performed silently by
the normal loader.

The foundation loader requires `config_schema_version`. An unversioned config fails with
`ConfigMigrationRequiredError`. An unsupported version also fails unless a reviewed migration is
registered for the exact source and target pair.

## Current state

```text
current_schema=1.0.0
registered_migrations=0
legacy_bulk_migration=NOT_PERFORMED
```

Existing repository YAML files remain under their current loaders and schemas. They must not be
rewritten merely to satisfy this foundation PR.

## Adding a future migration

A later PR should:

1. define the new schema and version;
2. add a pure migration function that accepts and returns dictionaries;
3. register only the exact `(source_version, target_version)` pair;
4. preserve the input object and operate on a copy;
5. set the target `config_schema_version` explicitly;
6. reject ambiguous, lossy, or unknown fields rather than guessing;
7. add golden input/output fixtures and SHA-256 evidence;
8. document changed semantics and rollback;
9. keep migration separate from Holdout/Prospective execution;
10. migrate selected configs in a later, explicitly scoped PR.

## Prohibited behavior

- no implicit migration during ordinary validation;
- no treating a missing version as the latest version;
- no best-effort key renaming;
- no silent default injection that changes experiment semantics;
- no secret persistence in migrated or resolved artifacts;
- no bulk rewrite of all YAML files in this foundation PR.

## Rollback

Before adoption, removing this foundation has no effect on existing loaders. After a workflow adopts a
specific schema version, rollback requires restoring both its prior loader and its prior versioned
configuration; do not relabel newer config bytes with an older schema version.
