# AutoGluon Runtime Inventory

Status: IMPLEMENTED / runtime execution pending in the isolated AutoGluon environment

## Purpose

The runtime inventory keeps four states separate:

1. `source_declared`: present in the pinned AutoGluon 1.5.0 source manifest;
2. `runtime_discovered`: present in `ModelRegistry.available_aliases()` or resolvable by
   `get_ensemble_class()`;
3. `runtime_importable`: the declared class can be imported in the active environment;
4. `runtime_certified`: fit/predict/save/load or ensemble lifecycle certification passed.

A model is never marked certified only because it appears in a registry.

## Source contract

- concrete model classes: 29;
- selectable ensemble names: 9;
- unique ensemble classes: 8;
- `Weighted` is an alias of `Greedy`;
- `PerformanceWeighted` is included.

The source manifest is intentionally pinned to AutoGluon TimeSeries 1.5.0. A version
mismatch produces `PARTIAL`, not an implicit manifest substitution.

## Failure classification

- `PACKAGE_MISSING`
- `OPTIONAL_DEPENDENCY_MISSING`
- `VERSION_MISMATCH`
- `IMPORT_ERROR`
- `SOURCE_CLASS_MISSING`
- `RUNTIME_ALIAS_MISSING`
- `UNKNOWN_RUNTIME_ALIAS`
- `ENSEMBLE_RESOLUTION_FAILED`

Unknown runtime aliases are retained in the artifact so upstream drift remains visible.

## Artifact

The JSON artifact contains a deterministic SHA-256 over the canonical inventory payload.
Writes use a temporary file followed by atomic replacement.

## Execution

Run from the repository root with the dedicated AutoGluon environment:

```bash
PYTHONPATH=src uv run \
  --project environments/autogluon-timeseries \
  python -m loto.autogluon_campaign.inventory_cli \
  --output artifacts/autogluon/runtime-inventory/inventory.json
```

Exit codes:

- `0`: `OK`;
- `1`: `PARTIAL` unless `--allow-partial` is supplied;
- `2`: `ERROR`.

## Certification boundary

This stage discovers and imports classes. It does not claim model execution, GPU usage,
accuracy, save/load parity, or Holdout/Prospective performance. Those remain later gates.
