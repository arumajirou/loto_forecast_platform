# Documentation map

Use this page to decide **which document is authoritative for which question**.

The repository contains both live design documentation and intentionally preserved point-in-time evidence. Reading every file as if it described the present is incorrect.

## Start here

| Question | Canonical entry point |
|---|---|
| What is the project and how do I use it? | [`../README.md`](../README.md) |
| What repository/project state was last audited? | [`STATUS.md`](STATUS.md) |
| How should stale/current/historical docs be interpreted? | [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md) |
| How many models are registered? | [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) and `loto3 catalog --counts` |
| What is the scientific evaluation contract? | [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) |
| What was the v3 implementation audit? | [`IMPLEMENTATION_STATUS_V3.md`](IMPLEMENTATION_STATUS_V3.md), historical report |
| How do I install on native Windows? | [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md) |
| What happened during the Windows-only PR #240 phase? | [`windows_only_execution/README.md`](windows_only_execution/README.md), historical execution bundle |

## Document classes

### Live entry points

These should remain useful on the current default branch and avoid volatile workstation assumptions:

- `README.md` at repository root;
- this `docs/README.md`;
- `docs/DOCUMENTATION_POLICY.md`;
- protocol/design documents whose contracts are still implemented.

### Audited snapshots

`docs/STATUS.md` is a point-in-time fact-check. It records its verification timestamp and audit base. It is not an auto-updating dashboard.

### Generated inventories

`docs/MODEL_INVENTORY.md` is generated and must not be hand-edited. The runtime catalog command is authoritative for current counts.

### Design contracts

Examples include:

- `docs/evaluation_protocol/**`;
- component `REQUIREMENTS.md` / `SPECIFICATION.md` / `ARCHITECTURE.md` / `DATA_CONTRACT.md` / `TEST_PLAN.md`;
- repository `specs/**` and `.specify/**` documents.

These define intended/implemented contracts. They must not embed local-machine availability as though it were part of the protocol unless that host identity is itself the explicit subject of the document.

### Historical evidence and handoffs

Many provider/component directories contain:

- `VERIFICATION_REPORT.md`;
- `HANDOFF.md`;
- `CHANGELOG.md`;
- `RUNBOOK.md` tied to a specific phase;
- certification CSV/JSON artifacts;
- exact Actions run IDs;
- model revision/hash manifests.

These are valuable precisely because they preserve what was observed at a specific SHA/time. Do not rewrite their underlying observation just because the project advanced. Add a supersession banner when needed.

### Immutable artifacts

`SHA256SUMS`, sealed protocol/prediction evidence and similar cryptographic artifacts are not prose status documents. They must never be silently regenerated in place to make old evidence look current.

## Scientific interpretation

The project separates:

```text
Registered
  -> Dependency available
  -> Runtime loadable
  -> Inference verified
  -> OOF evaluated
  -> Holdout eligible/evaluated
  -> Promotion eligible/promoted
```

Never infer a later level from an earlier one.

The primary scientific metric is Hit@±1. Formal evaluation also reports MAE, MSE, RMSE, position Hit@±1 and all-position Hit@±1, under leakage-safe chronological splits and complete multi-seed aggregation.

## Current Timer Base 84M boundary

See [`STATUS.md`](STATUS.md) for the audited snapshot. PR #240 is merged, but formal Timer Base 84M OOF, Holdout and Prospective work are not thereby complete.

Active scientific tracking:

- GitHub Issue #239;
- Linear TAJ-12.

The documentation alignment itself is tracked by PR #245 / Linear TAJ-13.

## Maintenance rule

When adding or updating a document that contains words such as `current`, `latest`, `today`, `open`, `running`, `available`, `blocked`, `PASS`, or a fixed run/SHA/count:

1. decide whether it is a stable contract or a point-in-time fact;
2. attach `as_of`/exact identity for point-in-time facts;
3. link to the live source or verification command;
4. follow [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md).
