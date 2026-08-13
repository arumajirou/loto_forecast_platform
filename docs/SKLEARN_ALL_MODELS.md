# scikit-learn all-estimator execution provider

Status vocabulary follows the repository rule: `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED`.

## Scope

The provider does **not** freeze a hand-written model list. It calls `sklearn.utils.all_estimators()` at runtime, so the execution denominator follows the installed scikit-learn version. This avoids silently omitting models added by newer compatible scikit-learn releases.

It supports classifier, regressor, cluster, transformer, and other estimator families. Required meta-estimator constructor arguments are supplied with deterministic lightweight child estimators for certification. Specialized estimators receive suitable deterministic synthetic inputs (binary/multiclass, multi-output, positive-only, pairwise, text, dictionary, and supervised transformer cases).

## Commands

```bash
uv run loto-sklearn list
uv run loto-sklearn list --kind regressor
uv run loto-sklearn smoke --model RandomForestRegressor --seed 1
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification
```

`certify` writes `sklearn_certification.json` with Python/scikit-learn versions, exact discovered denominator, per-estimator status, constructor evidence, selected operation, output shape, duration, and metrics when applicable.

For regressors, the smoke evidence includes MAE, MSE, RMSE and Hit@±1. For classifiers it includes accuracy. These synthetic smoke metrics are runtime evidence only and are **not** lottery OOF/Holdout/Prospective accuracy claims.

## Version behavior

The repository dependency remains `scikit-learn>=1.5`. The provider uses compatibility fallbacks for estimator tags and constructor parameter naming so the catalog is discovered from the installed version instead of assuming one fixed upstream denominator.

The previously frozen Broad-v1 seven scikit-learn identities remain unchanged. This provider is an additive dynamic execution/certification surface and must not be interpreted as automatically expanding the Broad-v1 scientific evaluation denominator.
