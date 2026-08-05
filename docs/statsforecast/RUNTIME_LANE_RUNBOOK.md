# StatsForecast 2.1.1 isolated runtime lane

This stacked increment depends on PR #51. It provisions a run-owned Python 3.13 environment
without changing the root project lock or installing StatsForecast into the root environment.

## Online execution

```bash
PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py certify \
  --output-root artifacts/statsforecast-runtime-lane
```

## Prepare a complete offline bundle

The preparation command resolves a fresh `uv.lock`, exports hash-pinned requirements, and
uses `pip download --require-hashes` to collect StatsForecast and every transitive dependency.
It then checks the selected StatsForecast wheel against the SHA-256 published in PyPI JSON.

```bash
PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py prepare-offline \
  --wheelhouse artifacts/statsforecast-offline-bundle

sha256sum -c artifacts/statsforecast-offline-bundle/SHA256SUMS
```

## Offline execution

```bash
PYTHONPATH=src python scripts/run_statsforecast_runtime_lane.py certify \
  --output-root artifacts/statsforecast-runtime-lane \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --offline
```

The offline runner verifies the bundle before use, copies the frozen `pyproject.toml` and
`uv.lock` into the run directory, performs `uv sync --locked` with indexes disabled, executes
all 41 checks from PR #51, and verifies the nested portable `SHA256SUMS`.

A PASS requires environment sync success, certifier exit code 0, and nested checksum PASS.
Network, resolver, package, model, lifecycle, bundle, or checksum failures return exit code 2
and preserve logs and `RUNTIME_LANE_REPORT.json`.
