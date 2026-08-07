# Runbook

## Validate a ledger

```bash
PYTHONPATH=src python -m loto.data_access_ledger.cli validate \
  --ledger /absolute/path/ledger.json \
  --report /absolute/path/validation-report.json
```

Interpret exit `0` as contract PASS, not real campaign certification. Exit `1` means the ledger is
BLOCKED or INVALID. Exit `2` means the file, JSON, output path, or environment prevented validation.

## Investigate failures

1. Preserve the original ledger; never overwrite Raw or evidence input.
2. Read each finding's code, event ID, related events, expected, and observed values.
3. Correct the event emitter or evidence source rather than editing the sealed ledger.
4. Generate a new ledger and SHA-256; retain the rejected ledger for audit.
5. Do not bypass Holdout/Prospective or state-provenance findings.

## Rollback

This foundation is isolated. Rollback consists of reverting the Data Access Ledger commit(s) or not
importing the package in an adoption PR. No schema migration, database rollback, model artifact
change,
or workflow change is required.
