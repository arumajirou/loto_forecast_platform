# StatsForecast runtime failure triage

Classify a completed end-to-end run and generate a deterministic remediation plan:

```bash
PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py triage-run \
  --end-to-end-dir artifacts/statsforecast-end-to-end/<run-id> \
  --output-dir artifacts/statsforecast-end-to-end/<run-id>-triage
```

Outputs:

- `FAILURE_CLASSIFICATION.json`
- `REMEDIATION_PLAN.json`
- `REMEDIATION_PLAN.md`
- `SHA256SUMS`

Primary classes are `NO_FAILURE`, `GIT_PREFLIGHT`, `CONFIGURATION`,
`DEPENDENCY_OR_NETWORK`, `MODEL_RUNTIME`, `EVIDENCE_INTEGRITY`,
`ADMISSION_REJECTED`, `TARGET_HOST_RUNTIME`, and `UNKNOWN`.

The progress percentage is an evidence-stage indicator, not predictive accuracy.
No remediation command is executed automatically. The command exits 0 only when the
source run is already `RUNTIME_CERTIFIED`; classified failures exit 2.
