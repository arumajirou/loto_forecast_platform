# StatsForecast target-host execution

Run this procedure on the Kubuntu or WSL host that contains the checked-out stacked branch.
It performs preflight capture, optional wheelhouse preparation, the exact 41-model runtime
certification, checksum verification, and a portable evidence ZIP.

## Online execution

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
git fetch origin
# Use the PR #62 worktree or branch without modifying main.
git switch agent/statsforecast-runtime-lane-v1

PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py target-host \
  --output-root artifacts/statsforecast-target-host \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --prepare-offline \
  --horizon 1 \
  --seed 1
```

## Offline execution

```bash
PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py target-host \
  --output-root artifacts/statsforecast-target-host \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --offline \
  --horizon 1 \
  --seed 1
```

The command exits 0 only for a formal PASS and exits 2 for a retained failure bundle.
It prints `CONTROLLER_DIR`, `ARCHIVE`, `ARCHIVE_SHA256`, and `STATUS`.

## Independent package verification

```bash
PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py verify-package \
  --archive artifacts/statsforecast-target-host/<run-id>.zip
```

The verifier checks the ZIP sidecar, path safety, duplicate members, checksum coverage, and
every archived file digest. Keep the ZIP and `.zip.sha256` sidecar together for handoff.
