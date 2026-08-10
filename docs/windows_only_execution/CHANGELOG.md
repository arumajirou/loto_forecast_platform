# CHANGELOG — Windows-only execution

## 2026-08-10

### Verified

- Restored self-hosted Windows runner `az-loto-windows` using actions-runner v2.336.0.
- Preserved runner identity as ID 22 while replacing the stale offline registration.
- Installed and started the Windows runner service under `NT AUTHORITY\NETWORK SERVICE`.
- Identified the first Windows portability failure as `ENVIRONMENT_FAILURE / MISSING_PWSH`.
- Installed PowerShell 7.6.4 machine-wide.
- Restarted the runner service so the service environment could resolve `pwsh`.
- Reran only the failed Windows job.
- Verified run `31353996850`, latest job `93356157095`, completed SUCCESS with 13/13 steps successful.

### Documentation alignment

- Updated root `README.md` with the current native-Windows-only operator constraint.
- Updated `docs/WINDOWS_INSTALL.md` with verified runner/PowerShell/CI evidence.
- Updated `docs/IMPLEMENTATION_STATUS_V3.md` with a 2026-08-10 current-project addendum.
- Updated `docs/evaluation_protocol/PROTOCOL_V2.md` to define Windows-native final protocol fixation requirements.
- Added the `docs/windows_only_execution/` documentation bundle.

### Scientific boundary unchanged

```text
formal_oof=false
timer_inference=false
holdout_opened=false
prospective_opened=false
accuracy_claim=false
champion_claim=false
promotion=false
```

### Next

Locate/transfer and hash-verify the frozen development snapshot on Windows, then regenerate final `EvaluationProtocolV2` artifacts against the final documentation/execution head before any formal OOF run.