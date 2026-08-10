# Documentation map

Use this page to decide **which document is authoritative for which question**.

The repository contains live code, generated inventories, isolated provider lanes, runtime evidence, design contracts and intentionally preserved historical reports. Reading every file as if it described one identical model surface is incorrect.

## Start here

| Question | Canonical entry point |
|---|---|
| What is the project and how do I use it? | [`../README.md`](../README.md) |
| What repository/project state was last audited? | [`STATUS.md`](STATUS.md) |
| How should stale/current/historical docs be interpreted? | [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md) |
| How many entries are in the broad generated catalog? | [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) and `loto3 catalog --counts` |
| Which models/libraries are actually wired to workers/providers/runtime evidence? | [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md) |
| What is the shared execution catalog? | `src/loto/models/catalog.py` and `loto models list` |
| What is the broad inventory catalog? | `src/loto/models/catalog_full.py` and `loto3 catalog` |
| What is the TSFM runtime evidence? | `audit/tsfm-runtime/runtime-status.json` and `audit/tsfm-runtime/<model>/runtime-certification.json` |
| What revisions were verified for the TSFM audit identities? | `configs/tsfm/verified-revisions.json` |
| What is the scientific evaluation contract? | [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) |
| What was the v3 implementation audit? | [`IMPLEMENTATION_STATUS_V3.md`](IMPLEMENTATION_STATUS_V3.md), historical report |
| How do I install on native Windows? | [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md) |
| What happened during the Windows-only PR #240 phase? | [`windows_only_execution/README.md`](windows_only_execution/README.md), historical execution bundle |

## The model surfaces are deliberately different

The codebase currently has at least these distinct surfaces:

```text
catalog_full.py
  broad inventory / 174 registered entries

catalog.py
  shared execution ModelSpec catalog

factory.py + workers.py
  normal shared in-process/worker execution

models/providers/**
  shared foundation provider registry

*_campaign/** + adapters/** + scripts/run_*_provider.py + environments/**
  isolated provider/campaign lanes

audit/**
  exact point-in-time runtime evidence
```

Do not use the 174-entry count as a synonym for “174 models are directly executable by `loto experiment research`”. Conversely, do not assume a provider is absent because it is not counted in the 174-entry broad catalog: BasicTS, Time-Series-Library, Merlion and several local NeuralForecast extensions have separate provider/campaign code.

For the concrete routing/status matrix, read [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md).

## Document classes

### Live entry points

These should remain useful on the current default branch and avoid volatile workstation assumptions:

- `README.md` at repository root;
- this `docs/README.md`;
- `docs/MODEL_EXECUTION_MATRIX.md`;
- `docs/DOCUMENTATION_POLICY.md`;
- protocol/design documents whose contracts are still implemented.

### Audited snapshots

`docs/STATUS.md` is a point-in-time fact-check. It records its verification timestamp and audit base. It is not an auto-updating dashboard.

### Generated inventories

`docs/MODEL_INVENTORY.md` is generated and must not be hand-edited. It describes the broad catalog. It does not replace the executable `ModelSpec` catalog, provider registry or runtime evidence.

### Runtime evidence

Runtime evidence is stronger than prose and stronger than registration for the exact identity it certifies. Examples:

- `audit/tsfm-runtime/runtime-status.json`;
- per-model `audit/tsfm-runtime/<model>/runtime-certification.json`;
- provider-specific request/response, environment, PID/GPU/VRAM and SHA-256 artifacts;
- exact-SHA GitHub Actions evidence.

Runtime certification still does not prove lottery-domain suitability, OOF improvement, Holdout success or promotion eligibility unless those later gates are separately evidenced.

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

## Capability interpretation

Use the following levels instead of a single ambiguous `available` flag:

```text
REGISTERED
  -> DEPENDENCY_DECLARED
  -> IMPLEMENTED
  -> SHARED_ROUTABLE or PROVIDER_ROUTABLE
  -> RUNTIME_CERTIFIED
  -> LOTTERY_COMPATIBLE
  -> OOF_EVALUATED
  -> HOLDOUT_EVALUATED
  -> PROSPECTIVE_EVALUATED
  -> PROMOTION_ELIGIBLE
```

Never infer a later level from an earlier one.

Examples from current code/evidence:

- `sktime` is in the broad catalog and frameworks extra, has a dedicated `sktime_campaign`, but is not a direct `PositionSeriesWorker` branch.
- `skforecast` is in the broad catalog/frameworks extra, but the audited shared worker has no direct skforecast dispatch.
- BasicTS and Time-Series-Library have real isolated provider code even though they are not represented as normal entries in the 174-entry broad count.
- the TSFM aggregate runtime evidence currently records 21 judged models, 19 `CERTIFIED`, 2 `BLOCKED`, while individual certification scopes still differ.

## Scientific interpretation

The primary scientific metric is Hit@±1. Formal evaluation also reports MAE, MSE, RMSE, position Hit@±1 and all-position Hit@±1, under leakage-safe chronological splits and complete multi-seed aggregation.

A runtime-certified model can still legitimately end with:

```text
NO_MODEL_BEATS_BASELINE
champion=null
```

Runtime success and scientific superiority are separate questions.

## Current Timer Base 84M boundary

See [`STATUS.md`](STATUS.md) for the audited snapshot. PR #240 is merged, but formal Timer Base 84M OOF, Holdout and Prospective work are not thereby complete.

Active scientific tracking:

- GitHub Issue #239;
- Linear TAJ-12.

The code-grounded model/library capability audit is tracked in Linear TAJ-14.

## Maintenance rule

When adding or updating a document that contains words such as `current`, `latest`, `today`, `open`, `running`, `available`, `blocked`, `PASS`, `certified`, or a fixed run/SHA/count:

1. decide whether it is a stable contract or a point-in-time fact;
2. attach `as_of`/exact identity for point-in-time facts;
3. identify the actual code/evidence source, not only another Markdown file;
4. distinguish registration, routing, runtime and scientific evidence;
5. link to the live source or verification command;
6. follow [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md).
