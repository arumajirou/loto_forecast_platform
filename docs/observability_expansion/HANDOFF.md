# Handoff

## Current state

This branch contains design documents only. Implementation has not started.

## First recommended implementation PR

```text
fix/evaluation-protocol-completeness-v1
```

This lane has no required external service dependency and resolves a direct scientific inconsistency:
the platform policy makes Hit@±1 primary while an existing research configuration defaults to position
MAE.

## Second recommended implementation PR

```text
feat/telemetry-contract-v1
```

Implement only contracts, redaction, correlation and metric cardinality policy. Do not add exporters or
deployment services in the same PR.

## Required preflight for every implementation PR

1. fetch latest main;
2. search open/closed PRs, branches and issues;
3. read PR #121, #123, #124/#129 and #127 status;
4. compare intended paths with current work;
5. stop on overlap;
6. create an independent Draft branch only after the audit.

## Explicit boundaries

Do not:

- extend PR #79 directly;
- create a new custom dashboard;
- modify PR #127 health behavior;
- redefine runtime certification;
- redefine Data Access Ledger events;
- add live service claims based on fake probes;
- open Holdout or Prospective;
- merge without explicit user approval.

## Evidence to retain

- commands and exit codes;
- exact base/head SHA;
- changed paths;
- dependency and container versions;
- test logs;
- service health and restart evidence;
- screenshots only as supplementary evidence;
- manifests and SHA-256;
- remaining non-claims.
