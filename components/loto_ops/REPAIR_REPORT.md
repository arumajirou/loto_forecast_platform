# Loto Ops Pipeline Repair Report

## Result

**PASS** — the repaired source passed the complete local test suite.

- Tests: **104 passed**
- Restored operations CLI: `preflight`, `run-all`, `run-all-fast`, `webapp`, `package`, and the remaining operations commands
- Preserved compatibility CLI: `run`, `export-handover`, `import-handover`
- Workflow A compatibility fix preserved: `workflow_dispatcher.py` SHA-256 `23e62032f14ff33519b7c3f4bc472738c363bfa48793e0b559146c515c013747`
- Canonical artifact implementation restored: `ManifestWriter`, `sha256_file`, `ArtifactPackager`

## Root causes corrected

1. Git HEAD contained the 718-line operations CLI but omitted the `loto_ops.artifacts` package.
2. The working CLI was reduced to 204 lines, removing operations commands.
3. The earlier generator validated multiline `add_parser()` calls using an invalid one-line string count and stopped before writing the candidate.
4. `.gitignore` used `artifacts/`, which also ignored `src/loto_ops/artifacts/`; it now uses `/artifacts/`.
5. Workflow A had conflicting compatibility contracts. `run()` retains the original behavior, while `dispatch()` returns `planner_plan=None` and writes handover data when configured.
6. Tests depended on external `/mnt/e/...` skill paths. The repair bundles the required skill definitions and makes test paths portable.

## Security and packaging

The clean distribution excludes runtime databases, logs, old backups, generated handovers, and `configs/notify.env`. The original `notify.env.example` contained live-looking credentials and was replaced by placeholders in the distribution.

## Validation performed

- Uploaded ZIP SHA-256 verified.
- Internal `SHA256SUMS` verified for every bundled file.
- ZIP traversal, absolute paths, duplicate members, and symlinks checked: no issues.
- Python `compileall`: PASS.
- CLI help checks for legacy and restored operations commands: PASS.
- Targeted CLI/session tests: PASS.
- Workflow contract tests: PASS.
- Skill schema tests: PASS.
- Full test suite: **104 passed**.

## Environment limitation during repair

The repair sandbox could not access a Python package registry, so `uv sync --frozen` could not download `hatchling`. Source-level imports and all tests were executed using the sandbox's existing Python environment. The supplied setup scripts perform the normal frozen `uv` installation on the destination machine.

## Distribution redactions

The downloadable archive replaces database and notification credentials with `CHANGE_ME`/example placeholders. Supply real values only through local ignored files or environment variables.


## v2 runtime corrections

- Added `PipelineOrchestrator.preflight()` with safe `--auto-fix`.
- Replaced the obsolete raw `runs_dir` dependency with `settings.paths.runs_dir`.
- Added automatic discovery of sibling `/mnt/e/env/ts` projects when legacy `/mnt/e/env/fc` paths do not exist.
- Pipeline failures now produce non-zero CLI exit codes instead of a misleading empty success.

## Runtime validation after user installation

The first distribution exposed three runtime-only defects that the initial help/pytest surface did not exercise:

1. `preflight` was registered in the restored CLI but absent from `PipelineOrchestrator`.
2. the legacy orchestrator read `settings.raw["runs_dir"]` even though the current settings model exposes `settings.paths.runs_dir`.
3. legacy `/mnt/e/env/fc` defaults were not automatically rebased to existing sibling projects under `/mnt/e/env/ts`.

The v2 repair adds structured preflight diagnostics, safe local-directory auto-fix, path auto-discovery, accurate non-zero failure propagation, and regression coverage. Final source validation: **110 passed**.
