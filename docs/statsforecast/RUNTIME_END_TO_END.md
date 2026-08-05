# StatsForecast end-to-end runtime gate

The end-to-end command joins target-host execution and package admission into one fail-closed
operation. It returns success only when the real StatsForecast 2.1.1 package passes all 41
model runtime contracts and the returned ZIP is admitted against the current clean commit.

The public API and CLI always inject the hardened admission inspector. The inspector first
runs the original package, commit, inventory, lifecycle, and checksum gate, then requires
point-mode CPU evidence for every model. Direct use of the unhardened base inspector is not a
formal End-to-End path.

```bash
PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py end-to-end \
  --output-root artifacts/statsforecast-end-to-end \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --prepare-offline \
  --expected-commit "$(git rev-parse HEAD)" \
  --horizon 1 \
  --seed 1
```

For an existing verified wheelhouse, replace `--prepare-offline` with `--offline`.

The command refuses a dirty working tree, a commit mismatch, mutually enabled online and
offline modes, or offline execution without a wheelhouse. It writes:

- `END_TO_END_REPORT.json`
- `END_TO_END_REPORT.md`
- `END_TO_END_EXCEPTION.json` when orchestration raises
- nested target-host and admission evidence
- `SHA256SUMS`

Exit code 0 means `RUNTIME_CERTIFIED`. Exit code 2 means `MERGE_BLOCKED`. The decision covers
runtime integrity only and does not certify predictive accuracy, Holdout results, or
Prospective results.
