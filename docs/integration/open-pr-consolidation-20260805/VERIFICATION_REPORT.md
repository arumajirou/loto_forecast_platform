# Open PR Consolidation Verification Report

## Status

`VERIFIED`

This report records the evidence and boundaries for consolidating open pull requests #13, #20, #21 and #35 into one reviewable integration pull request. It certifies repository integration and the executed GitHub Actions regression gate. It does not certify forecasting accuracy, GPU execution of every AutoModel, prospective performance, or a merge into `main`.

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
| verified feature-and-fix head | `e3c7c802ad5bee235255c64b643bc345ee5ebaae` |

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

PR #20 is a repository-wide formatting branch based on old `main` SHA `78a7fc41dae0d1c9a1ff6154e3a7991a5ea2ca08`. It reports no intended behavioral change and is not mergeable against current `main`. Current-main PR #34 passed repository-wide Ruff and full pytest. The integration CI also passes the current repository Ruff gates. Replaying PR #20 would risk reapplying obsolete deletions and formatting over newer implementations.

### PR #21 — do not replay

PR #34 explicitly ports PR #21 to current `main`. PR #34 merged as `3dfc6481a0d83eb578f5c0ec4c776e324f7aef1d` after focused tests, repository-wide Ruff, compileall, full pytest, secret scan and diff-integrity checks. PR #21 is superseded.

### PR #35 — integration source

PR #35 is based on the audited `main` SHA and contains the active Numbers4 NeuralForecast DB AutoModel workflow. Its previous GitHub Actions run passed dependency installation, Ruff format, Ruff lint and Python compileall, then failed during pytest collection before test execution.

Three module basenames were duplicated between `tests/auto_campaign/` and `tests/`:

- `test_contracts.py`
- `test_metrics.py`
- `test_registry.py`

The integration branch changes pytest to `--import-mode=importlib`, which imports test modules by their package/path identity rather than inserting the bare basename into `sys.modules`.

## Change introduced by the integration branch

```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib -q"
```

No forecasting model implementation, metric, dataset, prediction, seed, model ID or database schema was changed by this fix.

## Executed CI evidence

GitHub Actions run `30965165989` (workflow run number `321`) executed against pull-request merge commit `e7b27749e80bf897cf42de136ea71fc44249bc97`, whose integration head was `e3c7c802ad5bee235255c64b643bc345ee5ebaae`.

Job `92177436472` completed with `success`.

| Gate | Result | Evidence |
|---|---|---|
| checkout and Python 3.13 setup | PASS | step success |
| dependency installation | PASS | step success |
| Ruff format | PASS | `493 files already formatted` |
| Ruff lint | PASS | `All checks passed!` |
| Python compileall | PASS | step success |
| pytest collection | PASS | prior import-file mismatch absent |
| full pytest | PASS | progress reached 100%, process exit success |
| skipped tests | 3 observed | three `s` markers in progress output |

The successful run includes the AutoCampaign identity, OOF leakage, persistence, prediction-variant, formal-backtest and runtime-validation test areas present in the repository-wide suite.

### Non-failing warnings retained for follow-up

- PyTorch Lightning logging interval exceeds the one-batch smoke-training length.
- NumPy generic `timedelta` units are deprecated in several tests.
- NeuralForecast clamps `val_check_steps` when it exceeds `max_steps`.
- Optuna `TPESampler(multivariate=True)` is marked experimental.
- GitHub Actions reports Node.js 20 deprecation for actions forced onto Node 24.

These warnings did not fail CI and are not silently presented as resolved.

This report update is documentation-only. The latest pull-request head must also retain a green required workflow before merge approval.

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

## Non-claims

This work does not claim:

- improved prediction accuracy
- completed AutoModel campaign execution
- successful GPU inference for every model
- deterministic CUDA execution for every model
- successful live PostgreSQL or MLflow service connectivity
- final merge approval

## Rollback

Before merge, close the integration pull request or delete only the integration branch. After merge, revert the integration pull request merge commit. Do not rewrite `main` history or force-push.
