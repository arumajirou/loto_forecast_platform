# Strict Configuration Foundation Verification Report

## Status

```text
PARTIALLY_VERIFIED
FOUNDATION_IMPLEMENTED
FOCUSED_TESTS_PASS
PYTHON_COMPILE_PASS
LEGACY_CONFIG_MIGRATION_NOT_PERFORMED
FULL_REPOSITORY_VALIDATION_PENDING
GPU_NOT_EXECUTED
HOLDOUT_NOT_OPENED
PROSPECTIVE_NOT_EXECUTED
MERGE_NOT_PERFORMED
```

## Repository audit

- default branch: `main`;
- base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`;
- working branch: `agent/config-strict-schema-foundation-v1`.

The existing `ExperimentConfig` and Auto Campaign contracts already use `extra="forbid"`, but they do
not provide one global schema with strict types, environment override provenance, secret-redacted
resolved output, a protected-stage policy, or explicit migration control.

Observed existing defaults include:

- `ExperimentConfig.schema_version=2.1.0`;
- `ExperimentConfig` primary objective `mean_hits_at_7`;
- `ExperimentConfig` seeds `[42, 1729, 20260730]`;
- Auto Campaign model seeds `[1, 42, 2026]` and search seed `1`;
- Auto Campaign GPU resources with `accelerator=gpu` and `gpus_per_trial=0.25`;
- optional `mlflow_uri` in `ExperimentConfig`;
- Git commit and status collection in Auto Campaign runtime code.

These existing schemas and YAML files are unchanged by this PR.

Open PR review found many provider- or campaign-specific strict configs. No open PR implements this
repository-wide, adoption-neutral strict foundation with allowlisted environment provenance and
redacted resolved artifacts.

## Changed scope

Only new configuration-foundation paths are added:

```text
configs/configuration/strict_foundation.example.yaml
docs/configuration/CONFIG_CONTRACT.md
docs/configuration/MIGRATION_GUIDE.md
docs/configuration/VERIFICATION_REPORT.md
src/loto/configuration/__init__.py
src/loto/configuration/cli.py
src/loto/configuration/contracts.py
src/loto/configuration/loader.py
src/loto/configuration/migration.py
tests/configuration/test_strict_config_foundation.py
```

No existing experiment config, model config, result, root dependency, lockfile, API path, Holdout file,
or Prospective artifact is changed.

## Executed validation

Executed against the exact proposed foundation files in a dependency-light Python environment:

```text
pydantic=2.13.4
yaml=6.0.3
focused pytest=12 passed
python compileall=PASS
example CLI validation=PASS
resolved artifact write=PASS
resolved semantic SHA-256 and artifact sidecar=PASS
secret redaction=PASS
secret absent from resolved object representation=PASS
unknown-key rejection=PASS
strict-type rejection=PASS
range rejection=PASS
protected-stage rejection=PASS
explicit migration-required behavior=PASS
exact NEURALFORECAST_MLFLOW_TRACKING_URI mapping=PASS
duplicate environment target rejection=PASS
override provenance changes semantic hash=PASS
Python lines over 100=0
```

The focused tests cover required safe defaults, metrics, seed aggregation, environment provenance,
secret redaction, device/fallback distinction, fsynced atomic output, semantic and artifact SHA-256,
CLI output, and migration gates.

## Validation pending

The following are not represented as PASS:

| Validation | Status | Reason |
|---|---|---|
| Exact focused tests in full repository checkout | PENDING | Full private checkout unavailable locally |
| Full repository compileall | PENDING | Full private checkout unavailable locally |
| Existing config tests | PENDING | Full private checkout unavailable locally |
| Full pytest | PENDING | Not appropriate before focused integration validation |
| Ruff | PENDING | Tool availability to be checked after publication |
| mypy | PENDING | Tool availability to be checked after publication |
| GitHub Actions | PENDING | Inspect automatically triggered run; do not claim pre-step failure as code failure |

## Non-claims

This report does not claim that existing YAML configs conform to v1, that MLflow or Git metadata was
collected, that a GPU was used, that CPU fallback occurred, that Holdout or Prospective data was
opened, or that any model result changed.

## Safety

- no direct write to `main`;
- no force push;
- no Ready transition;
- no merge;
- no auto-merge;
- no bulk configuration migration.
