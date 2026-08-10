# Verification Report — Windows-only execution

Status date: 2026-08-10

## Overall status

```text
WINDOWS_OPERATOR_ENVIRONMENT=AVAILABLE
WINDOWS_SELF_HOSTED_RUNNER=PASS
WINDOWS_PORTABILITY_CI=PASS
ENGINEERING_IMPLEMENTATION_CI_GATES=7/7 PASS
FINAL_PROTOCOL_FIXATION=PENDING
FORMAL_OOF=NOT_STARTED
TIMER_INFERENCE=NOT_STARTED
HOLDOUT=UNOPENED
PROSPECTIVE=UNOPENED
```

## Verified facts

### PR #240 code-bearing state before documentation alignment

```text
state=open
draft=true
mergeable=true
last_code_bearing_head=7795c413d295f445dbdcdf8d85894bf6c81db35a
base=main
base_sha=10c6d633feb78a14c8832516e2e021d25bad5313
```

### Windows focused validation

On the code-bearing implementation contents:

```text
Ruff=PASS
Ruff_format=PASS
mypy=PASS
py_compile=PASS
focused_pytest=20/20 PASS
compileall_smoke=PASS
```

### Linux CI evidence

A standard Linux CI run passed for the code-bearing head. This is retained as historical environment-specific evidence. Linux is not currently available to the operator and is not assumed for subsequent steps.

### Native Windows runner recovery

Verified recovery facts:

```text
runner_name=az-loto-windows
runner_id=22
runner_version=2.336.0
runner_os=Windows
runner_arch=X64
runner_service_state=Running
runner_service_start_mode=Auto
runner_service_account=NT AUTHORITY\NETWORK SERVICE
runner_install_dir=C:\actions-runner
```

### PowerShell 7 environment failure and remediation

Initial Windows job failure:

```text
classification=ENVIRONMENT_FAILURE / MISSING_PWSH
message=pwsh: command not found
checkout_started=false
code_test_failure_demonstrated=false
```

PowerShell 7.6.4 was installed machine-wide, the runner service was restarted, and only the failed job was rerun.

### Native Windows portability CI final result

```text
run_id=31353996850
latest_job_id=93356157095
runner=az-loto-windows
status=completed
conclusion=success
steps=13/13 success
```

Verified lane coverage includes runner identity, checkout, exact uv, managed Python, committed lock validation, native Windows dependency resolution without Triton, wheel build, wheel install/import, tracked-files-clean, and post steps.

## What this does not prove

The successful portability lane does not prove:

- final `EvaluationProtocolV2` fixation;
- frozen development snapshot availability on Windows;
- formal baseline OOF results;
- formal Timer Base 84M accuracy;
- all provider/model runtime certification on Windows;
- Holdout or Prospective results;
- champion or promotion eligibility.

## Next evidence requirement

The next blocking evidence is the exact frozen development snapshot on Windows. Once present, verify its expected SHA-256, then regenerate all final protocols using Windows code/resource/package identity.

## Documentation update effect

This Windows-only documentation alignment advances the PR head with documentation-only commits. Any CI statement tied specifically to `7795c413...` remains evidence for the code-bearing tree at that point. The final documentation head must be re-fetched and its applicable CI checks reviewed before using the final PR head as the formal `git_commit` identity.