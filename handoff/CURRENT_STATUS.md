# Loto Forecast Runtime Audit Handoff

Updated: 2026-08-26T12:54:52.891725+09:00

## Current overall status

- estimated progress: `40%`
- Phase 4A Darts GPU smoke: `FAILED`
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`

## Phase 4A

- model: `None`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/darts-torch/.venv/bin/python`
- real data source: `None`
- real-data source SHA-256: `None`
- derived smoke-data SHA-256: `None`
- prediction shape/finite: `None` / `None`
- GPU PID observed: `None`
- peak provider VRAM MiB: `None`
- save/reload certified: `None`

## Evidence policy

Trained model binaries and derived real-data rows remain local. Git handoff contains only metadata, hashes, request/response, metrics, logs, and GPU evidence.

## Next

If VERIFIED, continue Phase 4B across the remaining ready queue. If FAILED, inspect Phase 4A evidence before modifying dependencies.
