# Windows-only execution bundle — historical PR #240 snapshot

> **Status class:** `HISTORICAL_EVIDENCE`  
> **Captured:** 2026-08-10 during PR #240 before merge  
> **Later-known PR state:** PR #240 merged as `0bb4680b2d26cfd32788381f580d86a4acd0fb6d`  
> **Audited repository state:** [`../STATUS.md`](../STATUS.md)

This directory preserves the operator-facing documentation created during the period in which the active operator could execute only on native Windows.

The phrase **Windows-only** describes that execution period. It is **not** a permanent repository support statement and must not be used to infer that Linux or WSL is unavailable in a later session.

## Captured state during PR #240

The bundle originally recorded:

```text
operator_environment_at_capture=native Windows only
linux_available_to_operator_at_capture=false
wsl_available_to_operator_at_capture=false
pr=240
pr_state_at_capture=open/draft
last_code_bearing_head_at_capture=7795c413d295f445dbdcdf8d85894bf6c81db35a
windows_runner=az-loto-windows
windows_runner_version=2.336.0
powershell=7.6.4
windows_ci_run=31353996850
windows_ci_latest_job_at_capture=93356157095
windows_ci_result=success
windows_ci_steps=13/13 success
engineering_gates=7/7 pass
scientific_progress=18%
formal_oof=false
timer_inference=false
holdout_opened=false
prospective_opened=false
```

These values are retained because they identify the evidence and operating context of that phase.

## Later-known state

By the documentation audit later on 2026-08-10:

```text
pr_240_state=merged
pr_240_merge_sha=0bb4680b2d26cfd32788381f580d86a4acd0fb6d
formal_oof=false
timer_inference=false
holdout_opened=false
prospective_opened=false
```

The merge updates the repository state; it does not rewrite the historical execution evidence above and it does not imply scientific completion.

## Documentation set

- `REQUIREMENTS.md` — requirements captured for the Windows-only execution phase
- `SPECIFICATION.md` — phase-specific formal protocol/OOF specification
- `ARCHITECTURE.md` — execution/evidence architecture for that phase
- `DATA_CONTRACT.md` — frozen snapshot and leakage boundary
- `TEST_PLAN.md` — phase verification sequence
- `VERIFICATION_REPORT.md` — facts verified in that phase
- `RUNBOOK.md` — Windows operator commands used/planned in that phase
- `HANDOFF.md` — continuation state at handoff time
- `CHANGELOG.md` — bundle changes

Treat these as point-in-time phase documents unless a file explicitly defines a portable/stable contract.

## Interpretation rules

- Historical Linux CI evidence remains valid for the exact SHA/run on which it was produced.
- Historical Windows CI evidence remains valid for its exact SHA/run.
- Neither proves a different host is currently available or unavailable.
- Formal protocol artifacts must bind the actual code/data/resource/package identities measured for the new run.
- Do not copy old host resource values into a new protocol merely to preserve a previous hash.
- Do not recreate a missing frozen data snapshot silently from a mutable database.
- Holdout and Prospective remain governed by their scientific gates.

For current interpretation and freshness rules, use [`../STATUS.md`](../STATUS.md) and [`../DOCUMENTATION_POLICY.md`](../DOCUMENTATION_POLICY.md).
