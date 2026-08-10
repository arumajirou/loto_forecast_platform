# Implementation Status v3.0.0 — historical verification report

> **Status class:** `HISTORICAL_EVIDENCE`  
> **Original verification date:** 2026-07-30  
> **Later PR #240 context captured:** 2026-08-10  
> **Live/audited project-state entry point:** [`STATUS.md`](STATUS.md)

This file preserves the v3.0.0 implementation verification and the later PR #240 transition context. It is **not** an auto-updating current-state page.

Operational facts that change independently of code — open PRs, current workstation OS availability, runner online/offline state, “latest” run IDs — must be re-fetched. See [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md).

## Later-known state after the PR #240 snapshot

The PR #240 documentation originally captured the PR while it was open/draft and while the active operator environment was native-Windows-only. Those were valid point-in-time facts.

By the 2026-08-10 documentation audit:

```text
PR_240_STATE=merged
PR_240_MERGE_SHA=0bb4680b2d26cfd32788381f580d86a4acd0fb6d
SCIENTIFIC_PROGRESS_FROM_PR_240=18%
FORMAL_OOF_RUN=false
TIMER_INFERENCE_RUN=false
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
ACCURACY_CLAIM=false
CHAMPION_CLAIM=false
PROMOTION=false
```

The workstation statement `CURRENT_OPERATOR_EXECUTION_ENVIRONMENT=native Windows only` is not a repository invariant and must not be carried forward as a permanent current fact. Repository evidence supports both self-hosted Linux standard CI and native Windows portability lanes; a formal scientific run must bind the identity of the host actually used.

## PR #240 engineering evidence boundary

PR #240 recorded the following engineering evidence before merge:

| Area | Recorded state | Evidence scope |
|---|---|---|
| Windows focused validation | PASS | 20/20 focused tests + Ruff + mypy + py_compile + compileall smoke on the PR code-bearing head |
| Standard Linux CI | PASS | exact historical PR-head run; environment-specific evidence |
| Native Windows self-hosted runner | PASS | runner and service evidence captured during the PR phase |
| Windows portability CI | PASS | run `31353996850`, job `93356157095`, 13/13 steps success |
| Native Windows lock/dependency resolution | PASS | committed universal lock, Windows resolution excluded Triton |
| Native Windows package smoke | PASS | wheel build + install/import |
| Formal Timer Base 84M OOF | NOT RUN | scientific gate remained closed |

These run IDs and host details are **exact-run historical evidence**, not permanent “latest” values.

## Scientific boundary preserved after merge

Engineering merge did not establish forecast superiority.

Still required before a formal Timer Base 84M accuracy claim:

1. immutable development snapshot identity and SHA-256;
2. chronological split/feature manifests;
3. final `EvaluationProtocolV2` fixation on the actual execution host;
4. mandatory baseline OOF under identical eligible folds;
5. Timer Base 84M OOF under the same protocol;
6. complete configured seed inventory;
7. Hit@±1-first reporting plus MAE/MSE/RMSE, position Hit@±1 and all-position Hit@±1;
8. prediction-before-actual sealing evidence;
9. independent artifact verification;
10. explicit later gates before Holdout or Prospective access.

## Original v3.0.0 verification snapshot — 2026-07-30

Original overall classification:

```text
VERIFIED (light environment)
NOT_CERTIFIED (external dependencies/providers not universally certified)
```

The light environment covered numpy / pandas / pydantic / scikit-learn / scipy / PyYAML / prometheus-client / fastapi / pytest / optuna for the then-current implementation surface.

### Historical verified values

| Metric | Historical value | Original method |
|---|---:|---|
| pytest | 313 passed / 0 failed | `pytest -q` in that v3 snapshot environment |
| coverage | 75% (3995/5328 statements) | `pytest --cov=src/loto` |
| registered models | 174 | `loto3 catalog --counts` |
| supported game geometries | 6 / 6 | game coverage tests |
| test hermeticity | same verdict with/without optional Optuna availability after fix | uninstall/rerun verification |
| integrity manifest | one self-verifying manifest | `loto3 integrity check` |

Do not use the historical pytest/coverage counts as a claim about the current test suite size. The model count remains separately generated in [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md).

## v2.1.0 defects detected and v3 responses

| # | Defect found in the historical audit | Response |
|---|---|---|
| 1 | stale `verification/SHA256SUMS` with mismatches | consolidated integrity handling and stale/untracked detection |
| 2 | broad exception handling made verdict depend on Optuna availability | narrowed import handling and declared dev dependency |
| 3 | pace gate / promotion / calibrators / stacking not connected | wired into research path |
| 4 | hard-coded game geometry | centralized in `GameGeometry` |
| 5 | provenance quality gate allowed all-null origin fields | added provenance validation |
| 6 | low coverage in central research path | implemented/expanded v3 core |
| 7 | inconsistent model aggregation | computed catalog counts |
| 8 | TSFM repo/revision reproducibility gap | added repo identity and explicit `UNPINNED` state rather than fabricated SHA |
| 9 | stale generated OpenAPI artifact | removed duplicate stale source |
| 10 | robots/ToS access checks missing | added data access checks |

Subsequent PRs materially expanded and repaired the repository beyond this original snapshot. For present repository state, start at [`STATUS.md`](STATUS.md), not this table.

## Certification interpretation

Neither the 2026-07-30 light-environment verification nor the later PR #240 portability evidence alone certifies:

- every optional dependency group;
- every model/provider runtime;
- every CUDA path;
- all Ray/Optuna/provider-specific runtime behavior;
- production deployment equivalence;
- Holdout/Prospective performance;
- champion or promotion eligibility.

A catalog entry is not runtime certification. A successful runtime is not forecast-quality evidence. OOF completion does not automatically authorize Holdout.

## Scientific position

The platform does not claim predictive advantage without executed evidence. Formal claims require fixed protocol/data/code identity, leakage checks, required baseline comparison, complete multi-seed aggregation, prediction sealing and the required runtime evidence.
