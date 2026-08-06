# Evidence Index Design

## Principle

GitHub is an index, not the evidence warehouse.

## Index layers

### Run index

- one Run ID;
- plan/code/data/protocol identities;
- execution summary;
- required evidence entries;
- completion and reconciliation status.

### Campaign index

- included Run IDs;
- selection rule;
- aggregate evaluation;
- campaign manifest and release identity.

### Prospective index

- prediction-lock bundle;
- trusted time status;
- Actual source/lock;
- post-reveal score;
- no pre-reveal Actual access.

## Storage mapping

| Artifact | Store | GitHub content |
|---|---|---|
| plan | Git | full strict YAML/JSON |
| small result summary | Git | full JSON |
| model weights | Object Storage | hash/URI only |
| raw data | immutable data store | hash/URI only |
| large predictions | Parquet/Object Storage | hash/URI only |
| full logs/traces | Loki/Tempo/Object Storage | link/hash only |
| metrics | MLflow/PostgreSQL | summary/link |
| temporary transfer | Actions artifact | expiry and hash |

## Verification

Index verification reopens remote objects where credentials and network policy allow. A missing
remote object does not invalidate the historical index bytes but changes verification status to
`MISSING` and blocks formal completion/promotion.

## Retention classes

```text
TEMPORARY_TRANSFER
RUN_EVIDENCE
PROSPECTIVE_LOCK
ACTUAL_EVIDENCE
CAMPAIGN_RELEASE
AUDIT_LONG_TERM
```
