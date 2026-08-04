# HANDOFF

## Existing certified asset

The completed AutoTFT 147-model Holdout is retained as a persistence/runtime
pilot. It is excluded from the all-AutoModel completion count.

## New implementation

Apply `apply_all_auto_campaign.py` to the project. Then run repository-local
Ruff, mypy, pytest, P0 inventory, plan, and P1 smoke before starting the complete
campaign.

## Stop conditions

Do not continue to P2+ when any of the following occurs:

- runtime registry differs unexpectedly;
- default-config catalog has failures;
- a successful Trial lacks a checkpoint;
- load/predict differs;
- prediction or state is non-finite;
- CPU fallback is detected;
- P1 stage status is not PASS.

## Truthful status

A locally completed campaign can still be `PARTIAL_API_COVERAGE` because Spark
`distributed_config` is intentionally outside the local RTX 5070 Ti campaign.
