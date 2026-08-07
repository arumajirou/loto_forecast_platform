# k-DPP fixed-cardinality PR-A verification report

## Status

`PARTIALLY_VERIFIED / PR_A_IMPLEMENTED / RUNTIME_PENDING`

## Implemented

- strict request, response, chronology, and configuration contracts
- CPU-only and no-fallback evidence schema
- game geometry for Numbers3, Numbers4, MiniLoto, Loto6, and Loto7
- diagonal-kernel degeneracy evidence
- deterministic canonical configuration hashing
- a private, non-registered model skeleton that fails closed for runtime operations
- focused contract and geometry tests

## Not implemented or executed

- public catalog or native registry registration
- real kernel fitting
- exact k-DPP prediction through the model lifecycle
- marginal inclusion probability calculation in the lifecycle
- save/reload and separate-process replay
- runtime PID evidence from a real model process
- OOF, Holdout, Prospective, Hit@±1, or baseline comparison
- GPU execution

## Acceptance boundary

Importability, schema validation, and synthetic contract fixtures are not formal runtime success.
PR-B must consume historical Train data, construct and validate a real PSD kernel, sample exact
fixed-k subsets, persist state, reload it in a second process, and reproduce a sealed prediction
before catalog registration is considered.
