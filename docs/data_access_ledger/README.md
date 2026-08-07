# Data Access Ledger v1

Status: `PARTIALLY_VERIFIED / STATIC_DATA_ACCESS_LEDGER_IMPLEMENTED / PIPELINE_INTEGRATION_PENDING`

Data Access Ledger v1 is a dependency-light, static contract and pure validator for recording which
process used which immutable dataset range, role, state, and forecast origin. It is designed to
reject
fit-scope violations, chronology violations, state provenance mismatches, future availability, and
Prospective ordering errors before adoption by existing pipelines.

## Components

- `enums.py`: stable v1 vocabulary.
- `contracts.py`: strict Pydantic v2 contracts.
- `canonical.py`: canonical JSON and SHA-256 sealing.
- `validator.py`: pure fail-closed validation.
- `report.py`: machine-readable findings and reports.
- `cli.py`: `python -m` validation entrypoint.
- `configs/data_access_ledger/example_ledger.json`: synthetic PASS fixture.

## Usage

```bash
PYTHONPATH=src python -m loto.data_access_ledger.cli validate \
  --ledger configs/data_access_ledger/example_ledger.json \
  --report /tmp/data-access-ledger-report.json
```

Exit codes are `0=PASS`, `1=INVALID/BLOCKED`, and `2=CLI input or environment error`.

## Explicit non-claims

This PR implements a static ledger contract and validator only. It does not integrate existing
pipelines, access real Train/Validation/Holdout/Prospective data, open Holdout, execute Prospective
forecasting, implement prediction-lock cryptography, trusted timestamps, actual-source
certification,
runtime certification, PostgreSQL/MLflow persistence, Registry, or promotion. Fixture PASS is not
certification of a real leakage-free campaign.
