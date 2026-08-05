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

The formal gate requires the exact ordered 41-name upstream 2.1.1
`statsforecast.models.__all__` surface and verifies that every pinned class is present. A
reordered, duplicated, missing, or extra export keeps the inventory unverified.

The formal 41-model matrix is point-forecast certification. It passes `level=None`; interval
levels are never requested implicitly. Interval execution is a separate explicit opt-in and is
not certified by this gate.

Every model row records CPU execution evidence:

- `device=cpu` and `device_type=cpu`;
- `gpu_not_applicable=true`;
- `gpu_pid=null` and `vram_mb=null`;
- `cpu_fallback=false`;
- `n_jobs=1`.

Formal PASS also requires finite point outputs except the expected-negative `NaNModel`, exact
shape and series/horizon identity, no duplicate keys, and successful
`fit -> predict -> save -> load -> predict` equality for every ordinary model. Using
`--skip-lifecycle` is diagnostic only and can never produce formal PASS.

Generated evidence includes package file hashes, runtime inventory, a per-model JSON/CSV
matrix, predictions, model bundles, `VERIFICATION_REPORT.json`, `ARTIFACT_MANIFEST.json`,
and portable `SHA256SUMS`. A missing package, version mismatch, incomplete inventory, model
configuration failure, execution failure, shape/identity failure, missing device evidence, or
lifecycle mismatch keeps the run `PARTIALLY_VERIFIED` and returns process exit code 2.
