# Current Verification Report

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:20+09:00
repository: arumajirou/loto_forecast_platform
audit_main_sha: cc7ec5473730cfb18100bdfbb5228cf65e571b32
scope: repository merge batch + current executable/documentation state
```

## Verdict

```text
PR_248_UNIFIED_CAMPAIGN=MERGED_AND_VERIFIED
PR_244_CHECKOUT_V7=MERGED_AND_VERIFIED
PR_242_RAY_TUNE_UPDATE=MERGED_AND_VERIFIED
PR_243_FASTAPI_UPDATE=VERIFICATION_PENDING_AT_SNAPSHOT
PR_241_GROUPED_UPDATE=REBASE_OR_RECREATE_PENDING_AT_SNAPSHOT
HOLDOUT=NOT_OPENED
PROSPECTIVE=NOT_OPENED
CHAMPION=NOT_CLAIMED
PROMOTION=NOT_AUTHORIZED
```

## Verified merged changes

### PR #248 — unified all-model × all-game evaluation

Merged commit:

```text
aae45ba9294499f51cc5f1564de1c6ccf5814230
```

Exact pre-merge implementation head:

```text
c7c8a039e7aa1aef34fbfd0af8dc2c41f67945a2
```

Linux standard CI:

```text
run=31371724178
job=93401966841
conclusion=SUCCESS
```

Verified stages included repository Ruff format, Ruff lint, compileall, full pytest, clean-tree check and cleanup.

Native Windows portability:

```text
run=31371724143
job=93401967447
conclusion=SUCCESS
```

Verified stages included universal-lock validation, dependency resolution, wheel build, installed-wheel import and tracked-file cleanliness.

The merged feature provides `uv run loto3 campaign`. It does not establish a full real-data 174 × 6 accuracy result.

### PR #244 — actions/checkout v7

Merged commit:

```text
c12ca27048d25cdc869fa3cbbfa6e31c727eb529
```

Exact dependency/workflow head:

```text
b4ae1d8197ed4e4ed942ee327a75457ba296c046
```

Linux and native Windows exact-head jobs completed successfully before merge. The change touched the CI/self-hosted/Windows checkout action pin, not model, data or evaluation semantics.

### PR #242 — Ray Tune requirement

Merged commit:

```text
cc7ec5473730cfb18100bdfbb5228cf65e571b32
```

Latest rebased pre-merge head:

```text
8641a50b9881f9fcb9716674dae63b3c8e2d7f2a
```

Linux exact-head full CI:

```text
run=31373320815
conclusion=SUCCESS
```

Native Windows exact-head portability subsequently completed successfully:

```text
run=31373320763
conclusion=SUCCESS
```

The audited `pyproject.toml` now contains `ray[tune]>=2.56.1` in the `full` extra and the committed `uv.lock` reflects the update.

## Pending PR verification

### PR #243 — FastAPI 0.141.1

The PR was recreated on audited main with head:

```text
0f8a0ec9d560d19cb4ee370c3fd2cf667801022f
```

At snapshot time GitHub reported the PR mergeable, but current-head Linux and native Windows workflows were queued. Because this is an API dependency jump, queued checks are not represented as PASS.

### PR #241 — grouped routine dependencies

The PR touches both `pyproject.toml` and `uv.lock` and includes multiple runtime/dev dependency updates. At snapshot time it had not yet completed rebasing/recreation onto the latest Ray-updated main. It is therefore not represented as merge-ready.

## Unified campaign contract verified in code/tests

The merged campaign implements these controls:

- canonical six-game geometry;
- complete requested broad-catalog × game materialization;
- explicit fail-visible status for non-routable/unsupported/unavailable/failed combinations;
- Hit@±1 primary tolerance;
- per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE;
- seven mandatory baselines;
- all configured seeds retained with aggregate statistics including variance and worst seed/value;
- prediction lock written/fsynced and SHA-256 sealed before actual scoring read;
- single-use output directory;
- Holdout and Prospective not evaluated by this campaign.

## What this report does not verify

This report does not certify:

- a real six-game data snapshot;
- every third-party model's availability on the target host;
- every model's successful runtime on all games;
- all-model GPU execution;
- full real-data OOF results;
- Holdout results;
- Prospective results;
- a champion;
- promotion eligibility.

Runtime evidence, scientific evidence and documentation evidence remain separate evidence classes.

## Historical report handling

The root `VERIFICATION_REPORT.md` is a historical version-single-source verification snapshot and must not be interpreted as the current whole-repository report. Current readers should use this file plus `docs/STATUS.md`; historical observations are preserved rather than rewritten.
