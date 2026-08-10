# Documentation map

Use this page to decide **which document is authoritative for which question**.

The repository contains live code, generated inventories, isolated provider lanes, runtime evidence, design contracts and intentionally preserved historical reports. Do not read all Markdown as one undifferentiated current state.

## Start here

| Question | Canonical entry point |
|---|---|
| What is the project and how do I use it? | [`../README.md`](../README.md) |
| What repository/project state was last audited? | [`STATUS.md`](STATUS.md) |
| What are the current scientific/platform requirements? | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| What is the executable campaign/routing specification? | [`SPECIFICATION.md`](SPECIFICATION.md) |
| What is the current architecture? | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| What is the data/chronology/leakage contract? | [`DATA_CONTRACT.md`](DATA_CONTRACT.md) |
| What is the current test/merge/scientific gate plan? | [`TEST_PLAN.md`](TEST_PLAN.md) |
| What is the current handoff? | [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md) |
| What is the current merge/CI verification snapshot? | [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) |
| What runbook should I use now? | [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md) |
| What current docs are part of the control-plane set? | [`CURRENT_ARTIFACT_MANIFEST.md`](CURRENT_ARTIFACT_MANIFEST.md) |
| How do I run all-model × all-game development evaluation? | [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md) and `uv run loto3 campaign` |
| What changed in current model execution after the older detailed audit? | [`CURRENT_MODEL_EXECUTION_ADDENDUM.md`](CURRENT_MODEL_EXECUTION_ADDENDUM.md) |
| How should stale/current/historical docs be interpreted? | [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md) |
| How many entries are in the broad generated catalog? | [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) and `loto3 catalog --counts` |
| Which models/libraries were code-grounded in the detailed routing audit? | [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md) |
| What is the shared execution catalog? | `src/loto/models/catalog.py` and `loto models list` |
| What is the broad inventory catalog? | `src/loto/models/catalog_full.py` and `loto3 catalog` |
| What is the TSFM runtime evidence? | `audit/tsfm-runtime/runtime-status.json` and per-model runtime certification evidence |
| What is the formal scientific evaluation protocol? | [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) |
| How do I install on native Windows? | [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md) |

## Current evaluation surface

The merged development campaign is:

```bash
uv run loto3 campaign --output unused --plan-only
```

Real development run:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Canonical games:

```text
mini
loto6
loto7
bingo5
numbers3
numbers4
```

The campaign materializes every requested broad-catalog model × game pair exactly once. `matrix_complete=true` means coverage is complete; it does **not** mean every combination succeeded. Unsupported, unavailable, non-routable, failed and non-standalone rows are retained as evidence.

Primary tolerance is Hit@±1. Required accompanying metrics include per-position Hit@±1, all-position Hit@±1, MAE, MSE and RMSE. Mandatory baselines and all configured seeds remain part of the formal comparison contract. Holdout and Prospective are separate closed gates unless independently authorized.

## Decoder/routing state

PR #249 added explicit `MAP` and `WITHIN_TAU` constrained select-game decoding. PR #250 connected probability-bearing unified-campaign candidate estimators to family-specific WITHIN_TAU decoding while leaving point-only workers point-only.

Probability-bearing candidate routes preserve explicit distribution/decoder identity. The row-normalized slot-binary candidate distribution is not mislabeled as a native categorical PMF.

This is implementation/routing evidence, not proof of real OOF improvement or non-IID lottery structure.

## Model surfaces are deliberately different

```text
catalog_full.py
  broad generated inventory / 174 registered entries at the audited inventory boundary

catalog.py
  shared executable ModelSpec catalog

factory.py + workers.py
  normal shared candidate / position / foundation execution

evaluation/unified_campaign.py + unified_campaign_cli.py
  broad inventory × canonical-game fail-visible development campaign

models/providers/**
  shared foundation provider registry

*_campaign/** + adapters/** + environments/**
  isolated provider/campaign lanes

audit/**
  exact point-in-time runtime evidence
```

Therefore:

```text
174 registered
!= 174 shared-routable
!= 174 runtime-certified
!= 174 OOF-evaluated
!= 174 promotable
```

Do not infer provider absence merely because it is not represented as a normal broad-catalog forecast entry; several libraries have separate isolated provider/campaign paths.

## Document classes

### Live entry points

These should stay useful on current main:

- root `README.md`;
- this `docs/README.md`;
- `REQUIREMENTS.md`;
- `SPECIFICATION.md`;
- `ARCHITECTURE.md`;
- `DATA_CONTRACT.md`;
- `TEST_PLAN.md`;
- `CURRENT_RUNBOOK.md`;
- `DOCUMENTATION_POLICY.md`;
- `UNIFIED_EVALUATION_CAMPAIGN.md`.

### Audited snapshots

`STATUS.md`, `CURRENT_HANDOFF.md`, `CURRENT_VERIFICATION_REPORT.md`, `CURRENT_MODEL_EXECUTION_ADDENDUM.md`, and `CURRENT_ARTIFACT_MANIFEST.md` are point-in-time fact checks. Their fixed SHA/run states require an `as_of` interpretation; live GitHub state wins later.

### Generated inventories

`MODEL_INVENTORY.md` is generated and must not be hand-edited. It describes the broad inventory, not shared routing, runtime certification, OOF or promotion.

### Runtime evidence

Runtime evidence is stronger than registration for the exact identity it certifies. Runtime certification still does not prove lottery-domain accuracy, OOF improvement, Holdout success or promotion eligibility.

### Historical evidence

Older `VERIFICATION_REPORT.md`, `HANDOFF.md`, CI run records and provider-specific artifacts should preserve what was observed at their exact SHA/time. Add a supersession pointer rather than rewriting old observations.

### Immutable artifacts

`SHA256SUMS`, sealed prediction/protocol evidence and similar cryptographic artifacts must not be silently regenerated in place to make old evidence look current.

## Capability interpretation

Use explicit stages:

```text
REGISTERED
-> DEPENDENCY_DECLARED
-> IMPLEMENTED
-> SHARED_ROUTABLE or PROVIDER_ROUTABLE
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
```

Never infer a later stage from an earlier one.

## Current scientific boundary

See [`STATUS.md`](STATUS.md) for the audited snapshot.

- Timer Base 84M formal leakage-safe OOF remains tracked in GitHub Issue #239.
- Timer-S1 immutable runtime/certification PR-B remains tracked in GitHub Issue #118.
- Unified campaign/decoder implementation does not open Holdout or Prospective and does not create a champion.
