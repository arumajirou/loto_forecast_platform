# Documentation map

Use this page to decide **which document is authoritative for which question**.

The repository contains live code, generated inventories, isolated provider lanes, runtime evidence, design contracts and intentionally preserved historical reports. Reading every file as if it described one identical model surface is incorrect.

## Start here

| Question | Canonical entry point |
|---|---|
| What is the project and how do I use it? | [`../README.md`](../README.md) |
| What repository/project state was last audited? | [`STATUS.md`](STATUS.md) |
| What is the current handoff for the next engineer/agent? | [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md) |
| What is the current merge/CI verification snapshot? | [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) |
| What operational runbook should I use now? | [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md) |
| How do I run the all-model × all-game development campaign? | [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md) and `uv run loto3 campaign` |
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

## Current executable evaluation surface

PR #248 merged the development-only unified campaign onto `main`.

```bash
uv run loto3 campaign --output unused --plan-only
```

For a real development run, provide canonical CSVs for all requested games and use a new output directory:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

The campaign materializes every requested broad-catalog model × game pair exactly once. `matrix_complete=true` means coverage is complete; it does **not** mean every combination succeeded. Unsupported, unavailable, non-routable, failed and non-standalone rows are deliberately retained as evidence.

The primary tolerance is Hit@±1. Required accompanying metrics include per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE. Mandatory baseline families and all configured seeds remain part of the evaluation contract. Holdout and Prospective stay closed unless separately authorized by their gates.

## The model surfaces are deliberately different

The codebase currently has at least these distinct surfaces:

```text
catalog_full.py
  broad inventory / 174 registered entries

catalog.py
  shared execution ModelSpec catalog

factory.py + workers.py
  normal shared in-process/worker execution

evaluation/unified_campaign.py + evaluation/unified_campaign_cli.py
  broad inventory × canonical-game fail-visible development campaign

models/providers/**
  shared foundation provider registry

*_campaign/** + adapters/** + scripts/run_*_provider.py + environments/**
  isolated provider/campaign lanes

audit/**
  exact point-in-time runtime evidence
```

Do not use the 174-entry count as a synonym for “174 models are directly executable by one legacy research command”, “174 models are runtime-certified”, or “174 models completed OOF”. Conversely, do not assume a provider is absent because it is not counted in the 174-entry broad catalog: BasicTS, Time-Series-Library, Merlion and several local NeuralForecast extensions have separate provider/campaign code.

For the concrete routing/status matrix, read [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md). For the common six-game adapter, read [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md).

## Document classes

### Live entry points

These should remain useful on the current default branch and avoid volatile workstation assumptions:

- `README.md` at repository root;
- this `docs/README.md`;
- `docs/MODEL_EXECUTION_MATRIX.md`;
- `docs/UNIFIED_EVALUATION_CAMPAIGN.md`;
- `docs/CURRENT_RUNBOOK.md`;
- `docs/DOCUMENTATION_POLICY.md`;
- protocol/design documents whose contracts are still implemented.

### Audited snapshots

`docs/STATUS.md`, `docs/CURRENT_HANDOFF.md` and `docs/CURRENT_VERIFICATION_REPORT.md` are point-in-time fact checks. They record their verification timestamps and audit bases. They are not auto-updating dashboards; live GitHub state takes precedence once time advances beyond their `as_of` value.

### Generated inventories

`docs/MODEL_INVENTORY.md` is generated and must not be hand-edited. It describes the broad catalog. It does not replace the executable `ModelSpec` catalog, provider registry, unified campaign result matrix or runtime evidence.

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

Examples from current code/evidence include:

- `sktime` is in the broad catalog and frameworks extra, has a dedicated `sktime_campaign`, but is not a direct `PositionSeriesWorker` branch;
- `skforecast` is in the broad catalog/frameworks extra, but the audited shared worker has no direct skforecast dispatch;
- BasicTS and Time-Series-Library have real isolated provider code even though they are not represented as normal entries in the 174-entry broad count;
- the TSFM aggregate runtime evidence records 21 judged models, 19 `CERTIFIED`, 2 `BLOCKED`, while individual certification scopes still differ.

## Scientific interpretation

The primary scientific metric is Hit@±1. Formal evaluation also reports MAE, MSE, RMSE, position Hit@±1 and all-position Hit@±1, under leakage-safe chronological splits and complete multi-seed aggregation.

A runtime-certified model can still legitimately end with:

```text
NO_MODEL_BEATS_BASELINE
champion=null
```

Runtime success and scientific superiority are separate questions.

## Current scientific boundary

See [`STATUS.md`](STATUS.md) for the audited snapshot. Formal Timer Base 84M OOF work remains tracked in GitHub Issue #239; Timer-S1 immutable runtime/certification work remains tracked in GitHub Issue #118. Neither the unified campaign merge nor dependency maintenance opens Holdout or Prospective.
