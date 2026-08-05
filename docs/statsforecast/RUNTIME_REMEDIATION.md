# StatsForecast bounded runtime remediation

This stacked lane consumes a verified failure-triage directory and performs only a bounded,
parameter-stable rerun of the existing end-to-end certifier.

It never executes command strings from `REMEDIATION_PLAN.json`, never mutates Git, never changes
seed or horizon, and never marks a pull request ready or merges it.

Automatic retries are allowed only for structured classifications that can be re-evaluated without
code mutation. `GIT_PREFLIGHT` and `UNKNOWN` stop as `MANUAL_ACTION_REQUIRED`.

```bash
PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_remediation.py \
  --repo-root . \
  --triage-dir artifacts/statsforecast-end-to-end/<run-id>-triage \
  --source-end-to-end-dir artifacts/statsforecast-end-to-end/<run-id> \
  --output-root artifacts/statsforecast-remediation \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --prepare-offline \
  --expected-commit "$(git rev-parse HEAD)" \
  --seed 1 \
  --horizon 1 \
  --max-attempts 1
```

The executor writes a plan, report, Markdown summary, portable checksums, deterministic ZIP, and ZIP
SHA-256 sidecar. Exit code 0 is reserved for an already-certified source or a successful
bounded rerun.
