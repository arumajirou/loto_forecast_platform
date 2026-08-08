# Windows Installation and Verification

## Status

`CURRENT_WITH_KNOWN_DEPENDENCY_LIMITATION`

Native Windows is an explicit repository portability target, but the current root dependency graph is not yet a fully certified native-Windows installation lane.

## Current blocker

`pyproject.toml` currently declares `triton==3.5.1` as an unconditional core dependency. That dependency is GPU/platform-specific and prevents treating a successful Linux/WSL resolution as proof that the same root environment resolves on native Windows.

Until the dependency boundary is remediated and verified:

- do not claim that `uv sync` for the complete root project is supported on every native-Windows host;
- do not delete or rewrite `uv.lock` merely to make one Windows machine resolve;
- do not silently omit Triton and call the resulting environment equivalent to the formal root environment;
- use environment-specific verification evidence and state which dependencies were intentionally absent.

## Repository operations

Git, GitHub CLI, documentation editing, static repository inspection, and other dependency-light repository operations can be performed natively on Windows without proving the full forecasting runtime.

Portable scripts should avoid hard-coded `/mnt/...` paths, user-specific `C:\...` paths, implicit Bash/PowerShell assumptions, shell-dependent subprocess construction, and case-sensitive/line-ending assumptions unless the behavior is explicitly platform-scoped.

## Forecast/runtime execution

For workflows that require the complete GPU/scientific dependency set, use an environment whose dependency resolution and runtime path are actually verified. Linux/WSL results remain environment-specific evidence and do not automatically certify native Windows.

Runtime certification must separately record load/inference/output/device evidence. Model availability or package installation alone is not runtime certification.

## Test guidance

Focused tests and smoke checks should be run in the smallest environment that honestly contains their required dependencies. Record any divergence from the root dependency graph, and do not represent such a focused environment as a full-project installation.

Repository-wide Windows installation certification remains pending until the unconditional platform-specific dependency boundary is fixed and the full install/test lane is executed successfully.
