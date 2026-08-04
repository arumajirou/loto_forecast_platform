# ARTIFACT_MANIFEST

## Source package

- `src/loto/auto_campaign/`: implementation modules.
- `configs/auto_campaign/`: campaign, coverage, resource, loss, and override
  configuration.
- `scripts/experiments/`: inventory, plan, run, monitor, tmux, and full campaign
  entrypoints.
- `tests/auto_campaign/`: focused contract, leakage, metrics, coverage, registry,
  persistence, and Trial persistence tests.
- `docs/NEURALFORECAST_ALL_AUTO_CAMPAIGN_SPEC.md`: authoritative copied design.
- `apply_all_auto_campaign.py`: idempotent repository installer.

## Documentation

`README.md`, `REQUIREMENTS.md`, `SPECIFICATION.md`, `ARCHITECTURE.md`,
`DATA_CONTRACT.md`, `TEST_PLAN.md`, `VERIFICATION_REPORT.md`, `CHANGELOG.md`,
`HANDOFF.md`, `RUNBOOK.md`, and this file.

## Integrity

`SHA256SUMS` lists every package file except itself. The distributed ZIP has a
separate `.sha256` file.
