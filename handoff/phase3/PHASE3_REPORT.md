# Phase 3 Runtime / Provider Route Mapping

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- Expanded v2 implementations: 244
- execution surfaces: 55
- source environments: 29
- Phase 2 raw runtime path candidates: 40
- canonical physical runtimes after realpath dedupe: 4

## Environment → runtime mapping

- `DIRECT_PROJECT_RUNTIME`: 10
- `EXISTING_RUNTIME_CANDIDATE`: 9
- `UNRESOLVED_NO_RUNTIME`: 10

## Execution surface → environment mapping

- `AMBIGUOUS_ROUTE`: 9
- `EXPLICIT_ROUTE`: 15
- `ROUTE_CANDIDATE`: 24
- `UNRESOLVED_EXECUTION_ENVIRONMENT`: 7

## Remaining uncertainty

- unresolved source environments: 10
- total mapping conflicts: 26
- Phase 2 extra runtime framework-import failures: 2

## Interpretation

`DIRECT_PROJECT_RUNTIME` means the source environment has its own host `.venv` detected in Phase 2.

`EXISTING_RUNTIME_CANDIDATE` means another existing runtime appears to match by family/name, but it has not yet been promoted to the formal runtime for that source environment.

`UNRESOLVED_NO_RUNTIME` means neither a direct runtime nor a sufficiently strong existing-runtime candidate was identified.

No checkpoint was loaded and no forecast was run in this phase.
