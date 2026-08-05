# Verification report

## Status

`PARTIALLY_VERIFIED / REAL_PINNED_DLINEAR_CPU_VERIFIED / ISOLATED_LOCK_BLOCKED`

## Revisions

- project base: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- upstream: `thuml/Time-Series-Library`
- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`

## Verified

- provider protocol and chronological split contract;
- Holdout and Prospective exclusion from training materialization;
- default pinned-source policy;
- fail-closed rejection of an unverified DLinear fixture;
- exact Git blob identity for upstream `models/DLinear.py`;
- exact Git blob identity for upstream `layers/Autoformer_EncDec.py`;
- real pinned DLinear CPU construct and three bounded fit steps;
- finite prediction and finite state dictionary;
- checkpoint save followed by load in a separate provider process;
- strict state-dictionary load;
- prediction shape `[2, 2, 3]` before and after reload;
- equal prediction SHA-256 before and after reload;
- equality within `rtol=1e-8`, `atol=1e-8`;
- maximum absolute reload error `0.0`;
- Python compileall and focused pytest: `6 passed`.

## Partially verified

Pinned GitHub code search returned 41 model modules with `class Model`. This is a
source-search inventory, not a complete local full-tree AST run. Every model other than
DLinear remains `EXECUTION_PENDING`.

## Blocked

The execution environment could not resolve GitHub DNS. `uv lock --offline` also failed
because `einops==0.8.1` was absent from the local uv cache. No isolated `uv.lock` was
created, and the root `uv.lock` was not modified.

## Runtime boundary

The real DLinear smoke used Python 3.13.5 and Torch 2.10.0 CPU already available in the
execution environment. The declared isolated lane targets Torch 2.9.1; execution in that
exact resolved environment remains pending.

## Not claimed

- all-model import, construction, training, or inference;
- GPU PID, VRAM, device, or no-CPU-fallback certification;
- Foundation Model or Mamba execution;
- real lottery Hit@±1, MAE, MSE, or RMSE;
- baseline superiority;
- Holdout or Prospective results;
- merge readiness.
