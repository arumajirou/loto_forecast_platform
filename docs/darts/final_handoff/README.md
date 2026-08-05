# Darts P1-P12 final handoff package

## Status

`PARTIALLY_VERIFIED / LOCAL_CONTRACTS_VERIFIED / REAL_PROVIDER_RUNTIME_BLOCKED`

This package hands off the isolated Darts forecasting work implemented on Draft PR #47.
It describes the P1-P12 contracts, the final verification boundary, and the commands needed
for the next operator to run the real cross-library campaign.

## Provenance

- repository: `arumajirou/loto_forecast_platform`
- base commit: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- P12 source commit: `b37dc3e463f95a1a8eced24cc99f4d14cc27fe67`
- target Darts version: `darts==0.46.1`
- package date: `2026-08-05`
- pull request: Draft PR #47

## Verified locally

P1-P12 documented focused runs total 108 tests. The final deterministic handoff package adds
10 focused tests. These tests were executed by increment and are not one combined 118-test
certification run.

The final package builder verifies required file names, canonical order, path safety, content
SHA-256 values, deterministic ZIP timestamps, normalized file modes, archive CRC, extraction,
and byte-for-byte equality with the source documents.

## Not yet verified

No real cross-library campaign has run with Darts, NeuralForecast, MLForecast, StatsForecast,
AutoGluon, and direct Foundation providers under the common fairness contract. Real GPU use,
provider compatibility, Holdout improvement, Prospective improvement, and a final champion
remain unverified.

Read `HANDOFF.md` first, then follow `RUNBOOK.md`.
