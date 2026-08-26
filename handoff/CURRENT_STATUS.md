# Loto Forecast Runtime Audit Handoff

Updated: 2026-08-26T13:00:11.795955+09:00

## Current overall status

- estimated progress: `44%`
- Phase 4A Darts GPU smoke: `VERIFIED`
- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`

## Phase 4A

- model: `DLinearModel`
- runtime: `/mnt/e/env/ts/loto_forecast_platform/environments/darts-torch/.venv/bin/python`
- real data source: `/mnt/e/env/ts/backups/loto-pre-consolidation-20260802-012717/loto_life_feature_pipeline/data/interim/bingo5_normalized.csv`
- real-data source SHA-256: `62a2c0984877c58593961052787469272e3f609e9c88472394cc0657c1248a9d`
- derived smoke-data SHA-256: `0ba9eac7c88670bbbc4cf0db65dc69eda5eb4b4cbcda2aedee32cd0bb0ea8489`
- prediction shape/finite: `True` / `True`
- GPU PID observed: `True`
- peak provider VRAM MiB: `352`
- save/reload certified: `True`

## Evidence policy

Trained model binaries and derived real-data rows remain local. Git handoff contains only metadata, hashes, request/response, metrics, logs, and GPU evidence.

## Next

If VERIFIED, continue Phase 4B across the remaining ready queue. If FAILED, inspect Phase 4A evidence before modifying dependencies.
