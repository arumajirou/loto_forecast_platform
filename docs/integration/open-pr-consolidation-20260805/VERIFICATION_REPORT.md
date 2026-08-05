# Open PR Consolidation Verification Report

## Status

`VERIFIED_UNMERGED`

This report records the evidence and boundaries for consolidating open pull requests #13, #20, #21 and #35 into one reviewable integration pull request. It certifies repository integration and the executed GitHub Actions regression gates. It does not certify forecasting accuracy, GPU execution of every AutoModel, prospective performance, or a merge into `main`.

## Immutable starting points

| Object | SHA |
|---|---|
| `main` at audit start | `3dfc6481a0d83eb578f5c0ec4c776e324f7aef1d` |
| PR #13 head | `2784781934900bc3a08bca49814d736514cea4ac` |
| PR #20 head | `fcaabd0993511f08bd92e9a54605eea426090808` |
| PR #21 head | `f834a3d6a9f396d0f2dbe06031640615fc26e263` |
| PR #35 source head | `03473ea869e91ea7253832e2900b0738bc769c71` |
| integration branch | `integration/consolidate-open-prs-20260805` |
| pytest collection fix | `5af130e63c8f863e2cc79d53f5c9b890114f8cc5` |
| local-metric grouping fix | `19aa082dd905bf68999680fba882444be401eeef` |
| local-metric regression test | `2e941da58adad8926ade210f7c740d73d9731f48` |
| Ruff formatting follow-up | `f96e015b8606066e23a6ca6d762cd24e3be2986b` |

## Scope decision

### PR #13 — do not replay

The critical implementation and environment files were compared by Git blob SHA between the PR head and current `main`.

| Path | Blob SHA | Result |
|---|---|---|
| `scripts/tsfm/run_granite_ttm_runtime_probe.py` | `ef862e47b5b4c368c289ec95b10a428538a459b1` | identical |
| `environments/granite-ttm/pyproject.toml` | `e6b0680726134ba2295f25fa60df05ddec4fe604` | identical |
| `environments/granite-ttm/run-python.sh` | `1f540519c9149a4cfcf7b6fc45842218016d2714` | identical |
| `environments/granite-ttm/uv.lock` | `91e7c50af5cd68f5232a07f1e8146ea24debfff9` | identical |
| `tests/test_granite_ttm_runtime_probe.py` | `ae331824eab0d06ce6e5d99cc791f9d98b544100` | identical |
| `audit/tsfm-runtime/granite-ttm-r2/runtime-certification.json` | `87a12fb765c86fbe97771de60b74b133a6803a05` | identical |

PR #15 and PR #16 subsequently integrated the broader TSFM certification ledger and complete evidence set. Replaying PR #13 would reintroduce old ledger and evidence snapshots and is therefore excluded.

### PR #20 — do not replay

PR #20 is a repository-wide formatting branch based on old `main` SHA `78a7fc41dae0d1c9a1ff6154e3a7991a5ea2ca08`. It reports no intended behavioral change and is not mergeable against current `main`. Current-main PR #34 and this integration branch pass repository-wide Ruff and full pytest. Replaying PR #20 would risk applying obsolete formatting and deletions over newer implementations.

### PR #21 — do not replay

PR #34 explicitly ports PR #21 to current `main`. PR #34 merged as `3dfc6481a0d83eb578f5c0ec4c776e324f7aef1d` after focused tests, repository-wide Ruff, compileall, full pytest, secret scan and diff-integrity checks. PR #21 is superseded.

### PR #35 — integration source

PR #35 is based on the audited `main` SHA and contains the active Numbers4 NeuralForecast DB AutoModel workflow. Its previous GitHub Actions run passed dependency installation, Ruff format, Ruff lint and Python compileall, then failed during pytest collection before test execution.

Three module basenames were duplicated between `tests/auto_campaign/` and `tests/`:

- `test_contracts.py`
- `test_metrics.py`
- `test_registry.py`

The integration branch changes pytest to `--import-mode=importlib`, which imports test modules by package/path identity rather than inserting the bare basename into `sys.modules`.

## Integration fixes

### Pytest collection isolation

```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib -q"
```

This fixes duplicate test basename collection without changing forecasting behavior.

### Preserve `config_index` in combined local-position metrics

A later code review identified that `_combined_local_metrics` grouped `u_local` prediction records by stage, model, seed, fold, origin and backend, but omitted `config_index`. Multiple fixed configurations could therefore be combined into one synthetic draw and corrupt Hit@±1, all-position Hit@±1, MAE, MSE and RMSE.

The fix:

- adds `config_index` to the grouping key
- retains the grouped `config_index` in the combined metric row
- adds `test_local_combined_metrics_preserve_config_index`
- creates two configurations across five positions and proves they are scored independently

No dataset, prediction payload, seed list, model ID, runtime device policy or database schema was changed by this repair.

## Executed CI evidence

### Initial integration verification

GitHub Actions run `30965165989` (workflow run number `321`) completed successfully on the feature-and-collection-fix head.

### Final metric-integrity verification

GitHub Actions run `30968439110` (workflow run number `329`) executed against integration head `f96e015b8606066e23a6ca6d762cd24e3be2986b` and pull-request merge commit `a745f63d564aa11b4a6df84cf12b6b872cd02d8c`.

Job `92187368630` completed with `success`.

| Gate | Result | Evidence |
|---|---|---|
| checkout and Python 3.13 setup | PASS | step success |
| dependency installation | PASS | step success |
| Ruff format | PASS | `493 files already formatted` |
| Ruff lint | PASS | `All checks passed!` |
| Python compileall | PASS | step success |
| pytest collection | PASS | prior import-file mismatch absent |
| full pytest | PASS | progress reached 100%, process exit success |
| local `config_index` regression | PASS | included in repository-wide suite |
| skipped tests | 3 observed | three `s` markers in progress output |

The successful suite includes AutoCampaign identity, OOF leakage, persistence, prediction variants, validation replay, formal backtest and runtime validation.

## Review resolution

The review thread concerning `config_index` was answered with the implementation commits and run #329 evidence, then marked resolved. At this report update there are zero unresolved review threads.

## Non-failing warnings retained for follow-up

- PyTorch Lightning logging interval exceeds the one-batch smoke-training length.
- NumPy generic `timedelta` units are deprecated in several tests.
- NeuralForecast clamps `val_check_steps` when it exceeds `max_steps`.
- Optuna `TPESampler(multivariate=True)` is marked experimental.
- GitHub Actions reports Node.js 20 deprecation for actions forced onto Node 24.

These warnings did not fail CI and are not silently presented as resolved.

## Required final gates

The integration pull request is acceptable only when all of these remain true on its final head SHA:

1. dependency installation succeeds
2. Ruff format succeeds
3. Ruff lint succeeds
4. Python compileall succeeds
5. pytest collection succeeds
6. full pytest succeeds
7. no unresolved review thread exists
8. GitHub reports the PR mergeable

A green workflow certifies repository integration and tests only. It does not certify GPU runtime, campaign completion, accuracy superiority, Holdout performance or Prospective Hit@±1.

## Time-series acceptance boundaries

The following contracts must remain true and are subject to code review and tests:

- chronological Train, Validation, Holdout and Prospective ordering
- scaler, encoder, feature selection and tuning fit only within Train/fold scope
- no future actual in prospective prediction payloads
- multiple seeds retained; no best-seed-only promotion
- Hit@±1 remains the primary metric with MAE, MSE, RMSE, position-wise and all-position metrics
- random, fixed, mean, median, recent, frequency and statistical baselines remain explicit
- prediction payloads are timestamped and SHA-256 sealed before actual disclosure
- no silent model substitution or backend fallback presented as success
- fixed configurations remain distinct through evaluation and ranking

## Non-claims

This work does not claim:

- improved prediction accuracy
- completed AutoModel campaign execution
- successful GPU inference for every model
- deterministic CUDA execution for every model
- successful live PostgreSQL or MLflow service connectivity
- Holdout or Prospective performance
- final merge approval

## Safety and rollback

No direct push to `main`, force push, auto-merge, source-branch deletion or merge was performed. Before merge, close the integration pull request to abandon it. After merge, revert the merge commit without rewriting `main` history.
