# AutoGluon TimeSeries Protocol v2 — Foundation Specification

Status: PROPOSED_IMPLEMENTATION / locally verified contract layer

## Scope

This batch introduces an AutoGluon-specific request/response contract and dynamic
lottery geometry without changing the common model catalog, common worker dispatch,
root CLI, root dependencies, or CI workflows.

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

## Deferred integration

The existing production dispatch remains in `src/loto/models/workers.py`, which is
outside this branch's ownership. Replacing protocol v1 requires a separately approved
shared-scope integration change after protocol v2 is complete and runtime-certified.
