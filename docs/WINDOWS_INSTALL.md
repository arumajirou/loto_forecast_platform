# Windows Installation and Verification

## Status

`CURRENT_WITH_NATIVE_WINDOWS_PORTABILITY_GATE`

Native Windows is an explicit repository portability target. The redundant unconditional root `triton==3.5.1` dependency was removed from `main` by PR #193, promoting the audited dependency fix from PR #182, and the locked PyTorch dependency now owns the platform boundary for Triton.

This removes the previous dependency-graph blocker, but it does **not** by itself certify the complete forecasting runtime on native Windows.

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

## Continuous Windows portability gate

`.github/workflows/windows-portability-ci.yml` is the repository's native-Windows portability lane. It runs on the repository's native Windows self-hosted X64 runner `az-loto-windows` and is intentionally narrower than the Linux/GPU runtime-certification lane.

The gate verifies:

1. exact `uv` version selection;
2. managed CPython 3.12.13 availability on the Windows runner;
3. `uv lock --check` against the committed universal lock;
4. native-Windows `uv sync --dry-run --locked` dependency resolution;
5. the Windows dependency tree does not select Triton;
6. the lock still contains the exact Linux x86_64 PyTorch -> Triton marker;
7. a native-Windows wheel build;
8. installation of that wheel with `--no-deps` into a Windows virtual environment;
9. `import loto` and package-version smoke verification.

The wheel smoke is deliberately dependency-light. It proves packaging/path behavior on native Windows without pretending that every forecasting, GPU, TSFM, Ray, database, or optional framework dependency has been installed and executed.

## Local PowerShell verification

For dependency-resolution verification from a native-Windows checkout:

```powershell
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

Git, GitHub CLI, documentation editing, static repository inspection, and other dependency-light repository operations can be performed natively on Windows without proving the full forecasting runtime.

Portable common-path code should avoid hard-coded `/mnt/...` paths, user-specific `C:\...` paths, implicit Bash/PowerShell assumptions, shell-dependent subprocess construction, and case-sensitive/line-ending assumptions unless the behavior is explicitly platform-scoped.

Historical audit evidence may legitimately contain environment-specific paths such as `/mnt/e/...`, `/home/...`, or Windows drive paths. Those recorded paths are evidence of the machine on which the run occurred and must not be rewritten merely to satisfy a portability scan.

## Forecast/runtime execution

For workflows that require the complete GPU/scientific dependency set, use an environment whose dependency resolution and runtime path are actually verified. Linux/WSL results remain environment-specific evidence and do not automatically certify native Windows.

Runtime certification must separately record model load, input, inference, output shape, finite values, device, GPU PID/VRAM when applicable, and CPU fallback behavior. Model availability or package installation alone is not runtime certification.

Linux-only deployment adapters such as systemd and explicitly Linux/GPU target-host workflows remain valid when their platform boundary is declared. They are not required to become native-Windows implementations.

## Remaining certification boundary

The native-Windows portability lane provides dependency-resolution and package-build/install smoke evidence only.

The following remain separate evidence requirements and must not be inferred from this gate:

- full root environment installation across every optional dependency group;
- full repository pytest PASS on Windows;
- model/provider runtime certification on Windows;
- CUDA/NVIDIA runtime certification on Windows;
- Ray/Optuna/framework-specific Windows certification;
- production deployment equivalence between Windows and Linux.

Any future native-Windows runtime claim must name the exact environment, dependency set, model/provider, device, and executed verification evidence.
