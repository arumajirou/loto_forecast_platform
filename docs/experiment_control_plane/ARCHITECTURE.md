# Architecture

## Context

```text
                    GitHub control plane
 Issue/Plan PR -> Controller API/CLI -> GitHub App -> Checks/Project/Result PR
                         |      ^
                         |      | outbound status/evidence references
                         v      |
                 Durable lifecycle store
                         | leased work
                         v
                 Local Experiment Agent
          local GPU / local CPU / paid API adapters
                         |
                         v
        MLflow / PostgreSQL / Parquet / Object Storage
                         |
                         v
       Prediction Lock / Actual / Evaluation / Promotion owners
```

## Trust boundaries

1. **Human/GitHub boundary**: editable Issues/comments are untrusted input. Only validated repository contracts and signed/recorded approval events may cross into execution authorization.
2. **Controller/agent boundary**: all commands are authenticated, schema-validated, idempotent and leased. The agent accepts only exact plan/subject hashes.
3. **Agent/model boundary**: model code, downloaded weights and external API responses are untrusted until identity, runtime, output shape and finite values are verified.
4. **Evidence/storage boundary**: URIs are locators, not proof. Bytes must be re-hashed; secrets in query strings are forbidden.
5. **Result/promotion boundary**: evaluation rank never implies approval, registry commit, canary or primary activation.

## Canonical authorities

| Concern | Canonical authority |
|---|---|
| Plan content | merged Plan file + commit SHA + canonical plan hash |
| Approval | append-only ApprovalRecord repository |
| Run lifecycle | PR #148 contract if merged; otherwise a dedicated compatible lifecycle repository |
| Data access | Data Access Ledger owner |
| Trusted time / Actual | PR #125 owner |
| Runtime certification | PR #123 owner |
| Evaluation | PR #138 / canonical evaluation protocol |
| Promotion | PR #137 / promotion governance |
| Full artifacts | evidence plane storage |
| GitHub Checks/Project | non-authoritative projections |

## Deployment topology

### Controller

Run as a local service initially, with PostgreSQL preferred for durable production use. SQLite/DuckDB may be used only for focused development and single-process smoke tests with explicit reduced guarantees.

### Agent

Run as a separate systemd user service or container with:

- no inbound internet listener required;
- outbound TLS to Controller/GitHub/object store as policy allows;
- per-lane Unix user or container boundary;
- workspace per Run ID;
- resource limits, timeouts, retry caps and secret mounts;
- JSON logs and externalized heartbeat state.

### GitHub App

Minimum permissions should be derived from exact operations. Expected initial permissions:

```text
Metadata: read
Contents: read
Issues: write (only if comments are used)
Pull requests: write (only if comments are used)
Checks: write
Actions: read
```

Projects permissions are added only if PR #145's live Project integration requires them. Tokens are short-lived and cached only until expiry.

## Data placement

| Data | GitHub | DB/MLflow | Object storage |
|---|---:|---:|---:|
| Plan and schema | yes | indexed | optional copy |
| Approval/event metadata | summary/reference | canonical | backup/export |
| Metrics/parameters | summary | canonical | report export |
| Predictions | hash/reference only | indexed | canonical bytes |
| Model weights | no | reference | canonical bytes |
| Raw data | no | catalog/reference | immutable canonical bytes |
| Logs/traces | small diagnostic excerpt | indexed | canonical/retained |
| Result summary | yes | canonical copy | bundle copy |
| Secrets | never | secret manager only | never in evidence |

## Availability behavior

- GitHub outage must not corrupt or lose a running experiment; projections catch up later.
- Controller outage stops new leases; an existing lease obeys bounded offline policy and cannot publish terminal success without reconciliation.
- Object-store outage blocks finalization but does not erase local sealed artifacts.
- MLflow outage is journaled; retry must not create duplicate runs when deterministic tags/IDs are supported.
- A zero-step GitHub Actions failure is classified as infrastructure blocked, not implementation failed.
