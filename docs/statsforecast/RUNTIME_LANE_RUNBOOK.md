# StatsForecast 2.1.1 isolated runtime lane

This stacked increment depends on PR #51. It provisions a run-owned Python 3.13 environment
without changing the root project lock or installing StatsForecast into the root environment.

## Online execution

```bash
PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py fetch \
  --wheelhouse artifacts/statsforecast-wheelhouse

PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py certify \
  --output-root artifacts/statsforecast-runtime-lane \
  --wheelhouse artifacts/statsforecast-wheelhouse
```

## Offline execution

Copy the complete wheelhouse, including `PYPI_RELEASE_SELECTION.json` and `SHA256SUMS`, to the
target host. Verify it before use, then run:

```bash
sha256sum -c artifacts/statsforecast-wheelhouse/SHA256SUMS

PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py certify \
  --output-root artifacts/statsforecast-runtime-lane \
  --wheelhouse artifacts/statsforecast-wheelhouse \
  --offline
```

The runner copies the isolated `pyproject.toml` into the run directory, resolves `uv.lock`,
syncs with `--locked`, executes all 41 runtime checks from PR #51, and verifies the nested
portable `SHA256SUMS`. Holdout and Prospective actual values are never opened.

A PASS requires environment lock and sync success, certifier exit code 0, and nested checksum
verification PASS. Network, resolver, package, model, lifecycle, or checksum failures return
exit code 2 and preserve logs and a `RUNTIME_LANE_REPORT.json` file.
