# Runbook

## 1. Checkout and inspect

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
git fetch origin
git switch feat/darts-forecasting-contract-v1
git status --short --branch
git rev-parse HEAD
git merge-base HEAD origin/main
git diff --stat origin/main...HEAD
```

## 2. Create isolated environments

```bash
uv sync --project environments/darts-notorch
uv sync --project environments/darts-torch
```

Do not modify root dependencies to resolve optional Darts conflicts.

## 3. Run focused tests

```bash
uv run pytest -q tests/darts_campaign
uv run python -m compileall -q src/loto/darts_campaign
uv run ruff check src/loto/darts_campaign tests/darts_campaign
uv run mypy src/loto/darts_campaign
```

If Ruff or mypy is unavailable, record the dependency or registry failure and do not report a
pass.

## 4. Execute real-provider smoke tests

For each provider, record package versions, model and revision, process PID, requested and
effective device, GPU PID, VRAM, input and output shapes, finite values, runtime, and failure
class. Do not continue to the full campaign when common fairness hashes differ.

## 5. Execute P12

Run eight outer provider tracks with a safe one-job GPU queue. Preserve identical folds and
seeds and complete prediction keys. Store per-seed metrics and aggregate mean, variance, and
worst values.

## 6. Seal prospective predictions

Write the canonical prediction payload, UTC timestamp, and SHA-256 before actual disclosure.
Make the sealed files read-only.

## 7. Build final handoff ZIP

```bash
uv run python -m loto.darts_campaign.final_package \
  --config configs/darts_campaign/final_handoff_package.yaml \
  --refresh-sha256s
sha256sum -c docs/darts/final_handoff/SHA256SUMS
```

The builder verifies the ZIP after writing it. Store the ZIP-level SHA-256 beside the archive.

## 8. Final quality gates

Run targeted tests, smoke tests, Ruff, mypy, pytest with coverage, and finally GitHub CI. Only
then consider Ready or merge, after explicit user approval.
