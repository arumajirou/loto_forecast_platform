# MLForecast handoff

## Current state

The source contract, leakage checks, metrics, runtime certifier, deterministic evidence bundler, and independent portable verifier are implemented. Local focused verification is complete. Exact installed-wheel runtime execution for the current head remains pending because the isolated environment cannot resolve the PyPI file host.

## First command on the target machine

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin
git switch feat/mlforecast-core-automl-contract-v1
git pull --ff-only origin feat/mlforecast-core-automl-contract-v1

bash docs/mlforecast/run_runtime_certification.sh
```

Do not merge or mark the PR ready based only on import success or model availability.

## Required success evidence

The runtime command must produce:

- exit status `0`;
- `RUNTIME_CERTIFICATION.json` with `status=RUNTIME_CERTIFIED`;
- finite Core Ridge and AutoRidge predictions;
- every requested AutoRidge trial complete;
- save/load key and value equality;
- runtime `ARTIFACT_MANIFEST.json` and `SHA256SUMS`;
- `<RUN_ID>.zip`, `<RUN_ID>.zip.sha256`, and `<RUN_ID>.verification.json`;
- external verification status `BUNDLE_VERIFIED`.

Upload or preserve all three bundle files together. The `.verification.json` does not replace the ZIP sidecar.

## Source handoff package

After the branch is committed and the MLForecast scope is clean:

```bash
bash docs/mlforecast/build_handoff_bundle.sh
```

The generated source handoff ZIP must verify as `HANDOFF_VERIFIED`. It contains required documents, source, tests, configuration, frozen provenance, snapshots of `pyproject.toml` and `uv.lock`, `ARTIFACT_MANIFEST.json`, `SHA256SUMS`, `SOURCE_PROVENANCE.json`, and `VERSION`.

## After runtime certification

1. Update `VERIFICATION_REPORT.md` and the PR body with the exact Run ID, package versions, wheel digest, CPU information, trial counts, prediction checks, ZIP digest, and verifier status.
2. Run Ruff format and lint in the target environment.
3. Inspect GitHub Actions once; do not start a rerun loop if the job again has zero steps.
4. Keep the PR in Draft until the exact runtime and focused tests pass.
5. Start the formal multi-seed campaign only after runtime certification.

## Formal campaign requirements

- time-ordered Train, Validation, Holdout, Prospective;
- same folds, features, and horizons across Core, Auto, statistical, neural, and baseline models;
- eight outer workers where safe, inner threads constrained;
- multiple seeds with mean, variance, and worst values;
- Hit@±1 primary plus MAE, MSE, RMSE, position-wise, and all-position metrics;
- sealed Prospective predictions before actual disclosure;
- no promotion based only on the best seed.

## Stop conditions

Stop and preserve evidence if any of the following occurs:

- wheel or metadata mismatch;
- installed version mismatch;
- duplicate, missing, non-finite, or out-of-order data;
- incomplete Optuna trials;
- output shape or finite-value failure;
- save/load key or value mismatch;
- bundle or handoff verification failure;
- unexpected shared-scope changes.
