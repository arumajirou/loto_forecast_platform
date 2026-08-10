# Windows-only execution status

Status date: 2026-08-10

This directory is the current operator-facing documentation bundle for the period in which only native Windows execution is available.

## Current facts

```text
operator_environment=native Windows only
linux_currently_available=false
wsl_currently_available=false
pr=240
pr_state=open/draft
last_code_bearing_head=7795c413d295f445dbdcdf8d85894bf6c81db35a
windows_runner=az-loto-windows
windows_runner_version=2.336.0
powershell=7.6.4
windows_ci_run=31353996850
windows_ci_latest_job=93356157095
windows_ci_result=success
windows_ci_steps=13/13 success
engineering_gates=7/7 pass
scientific_progress=18%
formal_oof=false
timer_inference=false
holdout_opened=false
prospective_opened=false
```

## Documentation set

- `REQUIREMENTS.md` — current execution requirements and stop conditions
- `SPECIFICATION.md` — Windows-native formal protocol and OOF specification
- `ARCHITECTURE.md` — current execution/evidence architecture
- `DATA_CONTRACT.md` — frozen snapshot and leakage boundary
- `TEST_PLAN.md` — verification sequence before formal OOF
- `VERIFICATION_REPORT.md` — facts verified as of this status date
- `RUNBOOK.md` — operator commands and decision flow
- `HANDOFF.md` — continuation state and next actions
- `CHANGELOG.md` — documentation/status changes

## Interpretation

Linux-specific artifacts and successful Linux CI remain valid historical evidence for the code-bearing head on which they were produced. They are not evidence that Linux is currently available, and their resource/package identity must not be copied into a new Windows formal protocol.

The next scientific gate is not model inference. It is Windows-side recovery or availability of the exact frozen development snapshot, SHA-256 verification, final `EvaluationProtocolV2` regeneration, and protocol-set fixation.