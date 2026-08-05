# AutoGluon TimeSeries Protocol v2 — Foundation Specification

Status: IMPLEMENTED_FOUNDATION / locally verified contract and inventory layers

## Scope

This batch introduces an AutoGluon-specific request/response contract, dynamic lottery
geometry, and pinned runtime inventory without changing the common model catalog, common
worker dispatch, root CLI, root dependencies, or CI workflows.

## Invariants

- schema and provider version are exactly 2;
- unknown request fields fail closed;
- default random seed is 1;
- explicit model modes require explicit model identities;
- preset AutoML cannot silently accept and ignore model IDs;
- every execution request carries a game geometry;
- prediction length equals the geometry horizon;
- source order is preserved and hashed;
- synthetic regular timestamps are mapped back to source order and timestamps;
- position count is defined by the contract, never by `range(1, 8)`;
- invalid, duplicate, out-of-range, non-finite, or unsorted values fail closed.

## Runtime inventory invariants

- the source manifest is pinned to `autogluon.timeseries==1.5.0`;
- source-declared, runtime-discovered, runtime-importable, and runtime-certified are
  separate states;
- source counts are 29 concrete models and 9 ensemble names / 8 unique classes;
- `Weighted` resolves to `GreedyEnsemble` and is recorded as an alias;
- `PerformanceWeighted` is included;
- unknown runtime aliases and missing source aliases fail to `PARTIAL`;
- package absence fails to `ERROR` without erasing the source manifest;
- inventory JSON is atomically written and protected by a canonical SHA-256.

## Deferred integration

The existing production dispatch remains in `src/loto/models/workers.py`, which is
outside this branch's ownership. Replacing protocol v1 requires a separately approved
shared-scope integration change after protocol v2 is complete and runtime-certified.

The common catalog remains unchanged. Runtime inventory is AutoGluon-private until a
separate shared catalog change is approved.
