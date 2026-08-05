# sktime P1 classic smoke matrix

## Status

```text
IMPLEMENTATION=COMMITTED_TO_DRAFT_PR
P0_CORE_LANE=core-py313
P1_CLASSIC_LANE=classic-py312
TARGET_SKTIME=sktime==1.0.1
REAL_P1_RUNTIME=EXECUTION_PENDING
ACCURACY_CLAIM=NOT_MADE
MERGE_READINESS=NOT_CLAIMED
```

P1 extends the isolated P0 contract from one Naive forecaster to four fixed,
reviewable forecasting configurations. It remains a runtime-certification
increment. It is not a chronological accuracy campaign and does not register
models in the shared worker or catalog.

## Why P1 uses Python 3.12

The exact sktime 1.0.1 project metadata restricts the curated forecasting
`statsmodels` dependency to Python versions below 3.13. The existing
`core-py313` lane therefore remains unchanged for registry discovery and the
Naive core smoke.

Theta and ExponentialSmoothing run in a second isolated environment:

```text
environments/sktime-classic-py312
Python >=3.12,<3.13
sktime==1.0.1
statsmodels>=0.14,<0.15
```

The root `pyproject.toml`, root `uv.lock`, shared workers, shared catalog, and
GitHub workflows remain unchanged.

## Formal model matrix

The request accepts only the following fixed IDs. Arbitrary import paths or
constructor dictionaries do not cross the JSON boundary.

| Model ID | Upstream class | Fixed constructor |
|---|---|---|
| `naive_last` | `NaiveForecaster` | `strategy="last"` |
| `polynomial_trend_d1` | `PolynomialTrendForecaster` | `degree=1`, `with_intercept=True` |
| `exponential_smoothing` | `ExponentialSmoothing` | `optimized=True`, `use_brute=False` |
| `theta` | `ThetaForecaster` | `deseasonalize=False`, `sp=1` |

Every model receives the same immutable univariate series, RangeIndex, relative
forecast horizon, CPU boundary, seed, and single-thread environment.

## Per-model phases

Each result retains separate states for:

```text
dependency
import
construct
fit
predict
save/load/re-predict
```

A model is `PASS` only when every requested phase passes. A missing distribution
is `UNAVAILABLE`; an import, construction, fit, prediction, persistence, shape,
index, or finite-value problem is `FAILED`.

Aggregate status is:

```text
PASS         all requested models passed
PARTIAL      at least one passed and at least one did not pass
UNAVAILABLE all requested models were unavailable
FAILED       no model passed and the failure set was not all unavailable
```

The provider CLI exits zero only for aggregate `PASS`.

## Formal P1 success gate

Formal P1 certification requires:

1. the isolated Python 3.12 lock resolves and is retained for review;
2. installed sktime is exactly `1.0.1`;
3. installed statsmodels is recorded;
4. Ruff format and lint pass;
5. compileall passes;
6. all focused sktime tests pass;
7. runtime registry inventory passes;
8. all four fixed models pass every phase;
9. prediction index and shape match the requested relative horizon;
10. all predictions are finite;
11. every saved model ZIP is non-empty;
12. load and re-predict complete;
13. pre-save and post-load predictions match exactly;
14. device is CPU and `cpu_fallback=false`;
15. provider manifests and SHA256SUMS verify;
16. top-level verification report and recursive SHA256SUMS verify.

One missing or failed model prevents formal P1 success.

## Start on the target Kubuntu host

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-forecasting-contract-v1
git switch agent/sktime-forecasting-contract-v1
git pull --ff-only

bash scripts/start_sktime_p1_matrix_certification_tmux.sh
```

The tmux wrapper refuses to replace an active session.

## Monitor

```bash
tmux attach -t sktime-p1-certification
```

Detach without stopping the run:

```text
Ctrl+B
D
```

## Inspect the latest result

```bash
ROOT="/mnt/e/env/ts/loto_forecast_platform"

RUN_DIR="$(
  find "${ROOT}/artifacts/sktime-p1" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%T@ %p\n' \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

printf 'run_dir=%s\n' "${RUN_DIR}"
cat "${RUN_DIR}/exit_code.txt"
cat "${RUN_DIR}/VERIFICATION_REPORT.json"
cat "${RUN_DIR}/smoke-matrix/SMOKE_MATRIX.json"

(
  cd "${RUN_DIR}" || exit 1
  sha256sum -c SHA256SUMS
)
```

## Artifact layout

```text
artifacts/sktime-p1/<run-id>/
├── RUN_METADATA.txt
├── UV_LOCK_SHA256
├── environment.json
├── inventory/
├── smoke-matrix/
│   ├── SMOKE_MATRIX.json
│   ├── response.json
│   ├── ARTIFACT_MANIFEST.json
│   ├── SHA256SUMS
│   └── *_model.zip
├── VERIFICATION_REPORT.json
├── ARTIFACT_MANIFEST.json
├── SHA256SUMS
├── logs/
└── exit_code.txt
```

Growing logs and the trap-created `exit_code.txt` remain audit evidence but are
excluded from the stable portable SHA seal. Stable requests, environment
identity, inventory, model evidence, reports, and model archives are sealed.

## Parallelism boundary

This four-case certification matrix executes serially with numerical thread
counts fixed to one. The purpose is phase isolation and reproducible evidence,
not throughput measurement. Eight-worker execution belongs to the later
chronological evaluation campaign, where trial scheduling, CPU oversubscription,
and fairness can be controlled explicitly.

## Certification boundary

P1 does not claim:

- runtime success until the target-host report is produced;
- execution of every discovered forecaster;
- optional models outside the fixed four-model matrix;
- intervals, quantiles, distributions, exogenous variables, panels, or
  hierarchical forecasting;
- Train/Validation/Holdout/Prospective evaluation;
- OOF, multiple seeds, HPO, or ensemble results;
- Hit@±1, MAE, MSE, or RMSE improvement;
- baseline superiority;
- MLflow or PostgreSQL persistence;
- GPU execution;
- common worker or catalog integration;
- repository-wide pytest or GitHub Actions success;
- merge readiness.
