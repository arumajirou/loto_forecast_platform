# StatsForecast runtime admission gate

The admission command evaluates a target-host ZIP after package integrity verification. It
never trusts an outer `PASS` field by itself and does not modify the submitted archive.

```bash
EXPECTED_COMMIT="$(git rev-parse HEAD)"
ARCHIVE="artifacts/statsforecast-target-host/<run-id>.zip"

PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py admit-package \
  --archive "$ARCHIVE" \
  --output-dir "${ARCHIVE%.zip}-admission" \
  --expected-commit "$EXPECTED_COMMIT" \
  --expected-seed 1
```

Exit code `0` means `RUNTIME_CERTIFIED`. Exit code `2` means `MERGE_BLOCKED`.

The gate requires all of the following:

- outer ZIP and sidecar SHA-256 verification;
- no ambiguous duplicate evidence files or special ZIP member types;
- Python 3.13, clean worktree, and the explicitly supplied Git commit;
- successful lock, sync, certification, wheelhouse, and nested checksum evidence;
- exact `statsforecast==2.1.1` package identity and hashed distribution files;
- exact 41-model export inventory, order, model matrix, and status counts;
- `NaNModel` as the sole expected-negative finite-value rejection;
- every other model `VERIFIED` with lifecycle, shape, identity, horizon, finite, and
  duplicate-key checks passing;
- `seed=1`, `n_jobs=1`, lifecycle validation enabled;
- Holdout unopened, Prospective actual unknown, and no accuracy-improvement claim.

Generated admission evidence:

- `ADMISSION_REPORT.json`
- `ADMISSION_REPORT.md`
- `SHA256SUMS`

The command does not merge, mark a PR ready, or certify predictive accuracy. It certifies
only the submitted package's runtime and evidence contract.
