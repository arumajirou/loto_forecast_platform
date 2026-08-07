# StatsForecast 2.1.1 runtime certification

Run the package-enabled certification only in an isolated environment containing the exact
`statsforecast==2.1.1` distribution. The command never opens Holdout or Prospective actuals.

```bash
PYTHONPATH=src python -m loto.statsforecast.certify \
  --output-root artifacts/statsforecast-runtime \
  --model-parameters configs/statsforecast/runtime_parameters.json \
  --horizon 1 \
  --seed 1
```

The formal gate requires all 41 names from the upstream 2.1.1
`statsforecast.models.__all__` surface, point forecast validation, finite outputs except the
expected-negative `NaNModel`, and `fit -> predict -> save -> load -> predict` equality.

Generated evidence includes package file hashes, runtime inventory, a per-model JSON/CSV
matrix, predictions, model bundles, `VERIFICATION_REPORT.json`, `ARTIFACT_MANIFEST.json`,
and portable `SHA256SUMS`. A missing package, version mismatch, incomplete inventory, model
configuration failure, execution failure, shape/identity failure, or lifecycle mismatch keeps
the run `PARTIALLY_VERIFIED` and returns process exit code 2.
