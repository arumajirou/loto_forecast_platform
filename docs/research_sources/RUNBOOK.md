# Runbook

## Validate the registry

```bash
cd /absolute/path/to/loto_forecast_platform
PYTHONPATH=src python -m loto.research_sources.cli \
  configs/research_sources/registry.v1.json \
  --report artifacts/research-sources/validation-report.json
```

Expected exit codes:

- `0`: schema and cross-record validation succeeded;
- `1`: invalid file, JSON, schema, or cross-record state.

## Review a source update

- compare old and new official URLs and immutable revisions;
- verify the canonical repository is official and not a mirror;
- verify every required path is safe and unique;
- independently hash downloaded bytes only in a later authorized snapshot workflow;
- preserve unresolved evidence with explicit sentinels;
- confirm code and weight licenses remain separate;
- confirm remote-code policy is present when required;
- inspect supersession links for cycles;
- rerun focused tests and manifest/SHA verification.

## Safety

Do not use this command to download packages or checkpoints. Do not open Holdout or Prospective
actuals. Do not modify active catalogs or production registries from this workflow.

Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.
