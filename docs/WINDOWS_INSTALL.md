# Windows Installation and Verification

## Status

```text
CURRENT_OPERATOR_ENVIRONMENT=NATIVE_WINDOWS_ONLY
NATIVE_WINDOWS_PORTABILITY_GATE=PASS
WINDOWS_RUNNER=az-loto-windows
WINDOWS_RUNNER_VERSION=2.336.0
POWERSHELL_VERSION=7.6.4
WINDOWS_PORTABILITY_RUN=31353996850
WINDOWS_PORTABILITY_LATEST_JOB=93356157095
WINDOWS_PORTABILITY_RESULT=SUCCESS
```

As of 2026-08-10, the project operator can execute only on native Windows. Linux and WSL evidence remains valid as historical, environment-specific evidence, but Linux/WSL must not be assumed available for the next formal run.

Native Windows is an explicit repository portability target. The root project does not declare Triton unconditionally; the committed universal lock keeps PyTorch's Triton edge Linux-x86_64-specific. A Windows dependency-resolution PASS is still narrower than complete forecasting/runtime certification.

## Current verified Windows host contract

The repository's native Windows self-hosted runner has been restored and verified:

```text
runner_name=az-loto-windows
runner_id=22
runner_version=2.336.0
runner_os=Windows
runner_arch=X64
runner_status=online
runner_service=actions.runner.arumajirou-loto_forecast_platform.az-loto-windows
runner_service_state=Running
runner_service_start_mode=Auto
runner_service_account=NT AUTHORITY\NETWORK SERVICE
runner_install_dir=C:\actions-runner
```

PowerShell 7 is a required workflow runtime because `.github/workflows/windows-portability-ci.yml` defines:

```yaml
defaults:
  run:
    shell: pwsh
```

The first recovered runner attempt failed before checkout with `pwsh: command not found`. This was classified as an environment failure, not a code or test failure. PowerShell 7.6.4 was then installed machine-wide, the runner service was restarted, and only the failed Windows job was rerun.

## Verified Windows portability result

The rerun succeeded:

```text
workflow=windows-portability-ci
run_id=31353996850
latest_job_id=93356157095
runner=az-loto-windows
result=success
steps=13/13 success
```

Verified steps:

1. Set up job;
2. verify expected native Windows self-hosted runner;
3. checkout without persistent credentials;
4. install exact uv;
5. verify uv and install managed Python;
6. validate committed universal lock;
7. resolve native Windows dependencies without installation;
8. build wheel on native Windows;
9. install wheel without dependencies and import package;
10. verify tracked files stayed clean;
11. post setup-uv cleanup;
12. post checkout cleanup;
13. complete job.

This establishes a strong native-Windows dependency/package portability gate. It does **not** by itself certify every forecasting model, CUDA path, Ray/Optuna path, database integration, or formal OOF run.

## Current dependency boundary

The root project no longer declares Triton directly. `torch==2.9.1` remains a root dependency, and `uv.lock` retains PyTorch's Triton dependency only for Linux x86_64:

```text
platform_machine == 'x86_64' and sys_platform == 'linux'
```

Therefore:

- native-Windows dependency resolution must not select Triton;
- Linux x86_64 dependency resolution may select Triton through PyTorch;
- the universal lockfile must remain a shared, reviewed artifact rather than being rewritten per host;
- a Windows dependency-resolution PASS is not equivalent to model/runtime certification.

## Current local Windows preflight

Use PowerShell 7 where possible:

```powershell
$PSVersionTable.PSVersion
uv --version
uv python install 3.12.13
uv lock --check
uv sync --dry-run --locked --python 3.12.13
uv tree --locked --python-version 3.12 --python-platform x86_64-pc-windows-msvc
```

The Windows tree must not contain Triton. Do not delete or hand-edit `uv.lock` to make a local machine resolve.

A dependency-light package smoke can be run with:

```powershell
uv build --wheel
uv venv .venv-portability --python 3.12.13
$wheel = Get-ChildItem dist\*.whl | Select-Object -First 1
uv pip install --python .venv-portability\Scripts\python.exe --no-deps $wheel.FullName
& .\.venv-portability\Scripts\python.exe -c "import loto; print(loto.__version__)"
```

## Repository operations

Git, GitHub CLI, documentation editing, static repository inspection, protocol generation, checksum verification, and other repository operations can be performed natively on Windows.

Portable common-path code should avoid hard-coded `/mnt/...` paths, user-specific `C:\...` paths, implicit Bash/PowerShell assumptions, shell-dependent subprocess construction, and case-sensitive/line-ending assumptions unless the behavior is explicitly platform-scoped.

Historical audit evidence may legitimately contain environment-specific paths such as `/mnt/e/...`, `/home/...`, or Windows drive paths. Those recorded paths are evidence of the machine on which the run occurred and must not be rewritten merely to satisfy a portability scan.

## Formal EvaluationProtocolV2 on Windows

The formal protocol is **not Linux-only**. It may be regenerated on Windows provided all identities are measured from the Windows execution context and the exact frozen development snapshot is available and SHA-256 verified.

For Timer Base 84M OOF, the next protocol fixation must:

1. bind the final PR Git commit;
2. calculate `code_hash` from the raw bytes of `git ls-tree -r --full-tree <HEAD>` without PowerShell text-encoding conversion;
3. verify the frozen development snapshot SHA-256;
4. preserve the 5-game × 2-layout × horizon-1 scientific design unless an intentional protocol change is recorded;
5. record Windows CPU/GPU/resource/package identity instead of copying historical Linux values;
6. keep Holdout and Prospective closed;
7. write new immutable protocol artifacts rather than overwriting historical artifacts.

A safe Windows code-hash implementation is Python bytes over Git output:

```powershell
@'
import hashlib
import subprocess

head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
payload = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", head])
print("git_commit=" + head)
print("code_hash=" + hashlib.sha256(payload).hexdigest())
'@ | python -
```

Do not hash a PowerShell-generated UTF-16/CRLF text rewrite of the tree listing.

## Runtime certification boundary

For any model/provider claiming native-Windows runtime success, record at least:

- model load success;
- validated input;
- inference execution;
- output shape;
- finite output values;
- device;
- GPU PID and VRAM where applicable;
- explicit CPU fallback behavior.

Model availability, dependency installation, or wheel import alone is not runtime certification.

## Remaining Windows-only execution work

Current verified infrastructure is sufficient to proceed without Linux, but the following remain unfinished:

- locate or safely transfer the frozen development snapshot to Windows;
- verify its exact SHA-256 before use;
- regenerate final `EvaluationProtocolV2` artifacts with Windows resource/package identity;
- fix the new protocol-set SHA-256;
- execute baseline OOF;
- execute Timer Base 84M OOF;
- aggregate all configured seeds by mean, variance, standard deviation, and worst value;
- report Hit@±1 first, plus MAE/MSE/RMSE, position Hit@±1, all-position Hit@±1;
- keep Holdout and Prospective unopened until their explicit gates.