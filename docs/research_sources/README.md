# Research Source Registry v1

## Status

```text
IMPLEMENTED_IN_ISOLATED_SCOPE
SOURCE_INTAKE_ONLY
RUNTIME_NOT_EXECUTED
PRODUCTION_NOT_ELIGIBLE
```

Research Source Registry v1 records the evidence required before a model or method implementation
PR may start. It is deliberately separate from the active model catalogs, provider dispatch,
runtime certification, data-access governance, Registry/Promotion backends, Holdout, and
Prospective workflows.

## Contents

- strict Pydantic v2 contracts under `src/loto/research_sources/`;
- 11 initial records in `configs/research_sources/registry.v1.json`;
- deterministic canonical JSON and registry SHA-256;
- a dependency-light validation CLI;
- focused fail-closed tests;
- design, contract, verification, runbook, handoff, and artifact-integrity documents.

## Validation

```bash
PYTHONPATH=src python -m loto.research_sources.cli \
  configs/research_sources/registry.v1.json \
  --report artifacts/research-sources/validation-report.json
```

A valid report means only that the source-intake document satisfies this schema and its internal
cross-record checks. It does not prove package resolution, checkpoint integrity, model load,
inference, forecast quality, commercial eligibility, or production eligibility.

## Initial records

| source_id | initial status |
|---|---|
| granite-flowstate | CHECKPOINT_REVIEW_REQUIRED |
| tempopfn-38m | CHECKPOINT_REVIEW_REQUIRED |
| kairos-10m | REMOTE_CODE_REVIEW_REQUIRED |
| kairos-23m | REMOTE_CODE_REVIEW_REQUIRED |
| kairos-50m | REMOTE_CODE_REVIEW_REQUIRED |
| reverso-small | CHECKPOINT_REVIEW_REQUIRED |
| granite-patchtst-fm | CHECKPOINT_REVIEW_REQUIRED |
| lightgts | LICENSE_REVIEW_REQUIRED |
| super-linear | LICENSE_REVIEW_REQUIRED |
| method-raft | CONDITIONAL |
| method-ts-rag | CONDITIONAL |

The conservative statuses are intentional. An official model card or repository is not sufficient
to claim a pinned checkpoint, reviewed dependency graph, remote-code safety, runtime success, or
commercial eligibility.

Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.
