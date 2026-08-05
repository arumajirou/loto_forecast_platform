# Integration Test Plan

## Objective

Verify that the active PR #35 feature set integrates with current `main` without replaying superseded PRs #13, #20 and #21, and that the previous pytest collection failure is resolved without changing forecasting behavior.

## Test order

1. Ruff format check
2. Ruff lint
3. Python compileall
4. pytest collection
5. focused AutoCampaign tests
6. full pytest
7. diff, secret and large-file inspection
8. semantic contract review

## Automated CI commands

The repository workflow is expected to execute the equivalent of:

```bash
python -m ruff format --check src scripts tests
python -m ruff check src scripts tests
python -m compileall -q src scripts tests
python -m pytest -q
```

The pytest configuration supplies `--import-mode=importlib`; command-line `-q` duplication is harmless but the final workflow log must show successful collection and execution.

## Focused checks

```bash
python -m pytest -q tests/auto_campaign
python -m pytest -q tests/test_contracts.py tests/test_metrics.py tests/test_registry.py
python -m pytest -q tests/test_neuralforecast_db_automodel.py
```

## Required semantic tests

The following existing tests are especially important:

- `tests/auto_campaign/test_oof_no_leakage.py`
- `tests/auto_campaign/test_runner_automodel_identity.py`
- `tests/auto_campaign/test_runner_code_fingerprint.py`
- `tests/auto_campaign/test_runner_verify_run.py`
- `tests/auto_campaign/test_trial_persistence.py`
- `tests/auto_campaign/test_validation_replay_ids.py`
- `tests/auto_campaign/test_baselines_excluded.py`
- `tests/auto_campaign/test_prediction_variants.py`

## Acceptance criteria

| Gate | Acceptance |
|---|---|
| Formatting | no files require reformatting |
| Lint | zero Ruff findings |
| Compile | zero syntax/import compilation errors |
| Collection | no import-file mismatch and no duplicate-basename collision |
| Full tests | exit code 0 |
| Diff | only PR #35 feature content, pytest isolation and audit documents |
| Secrets | no credential-like material in added lines |
| Large files | no newly added file at or above 95 MB |
| Prediction contract | no prospective actual disclosure and sealing contract retained |
| Promotion contract | no best-seed-only promotion and explicit baseline comparison retained |

## Failure handling

When a gate fails:

1. preserve the failing workflow URL and final head SHA
2. classify the failure layer
3. make the smallest isolated fix
4. verify the directly affected tests first
5. rerun the required CI once after the local-equivalent fix is complete
6. do not merge or enable auto-merge while any gate is non-green

## Certification boundary

Successful completion certifies code integration and regression tests. It does not certify accuracy improvement, full GPU execution, completed campaigns, live service connectivity or Prospective performance.
