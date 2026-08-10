# Documentation map

```text
status_class: LIVE_ENTRYPOINT
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
as_of: 2026-08-10T20:23+09:00
```

このページは、**どの質問にどの資料を正本として使うか**を示します。コード、generated inventory、runtime evidence、scientific evidence、historical reportを同じ「現在値」として扱わないでください。

## Start here

| Question | Canonical reference |
|---|---|
| このplatformで具体的に何ができるか | [`../README.md`](../README.md) |
| library/model/実行laneを詳しく引きたい | [`CAPABILITIES_AND_OPERATIONS.md`](CAPABILITIES_AND_OPERATIONS.md) |
| 現在のrepository/scientific状態 | [`STATUS.md`](STATUS.md) |
| 実際のmodel routing/runtime evidence | [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md) |
| broad generated catalog | [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md), `uv run loto3 catalog` |
| shared execution catalog | `src/loto/models/catalog.py`, `uv run loto models list` |
| all-model × all-game campaign | [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md) |
| formal evaluation protocol | [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) |
| requirements | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| external specification | [`SPECIFICATION.md`](SPECIFICATION.md) |
| architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| data/leakage contract | [`DATA_CONTRACT.md`](DATA_CONTRACT.md) |
| test/verification plan | [`TEST_PLAN.md`](TEST_PLAN.md) |
| current operations | [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md) |
| next-engineer handoff | [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md) |
| current merge/CI snapshot | [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) |
| current documentation artifacts | [`CURRENT_ARTIFACT_MANIFEST.md`](CURRENT_ARTIFACT_MANIFEST.md) |
| documentation freshness rules | [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md) |
| TSFM runtime evidence | `audit/tsfm-runtime/runtime-status.json` + per-model evidence |
| TSFM immutable revisions | `configs/tsfm/verified-revisions.json` |
| native Windows install | [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md) |

## Current platform surfaces

### Six-game geometry

```bash
uv run loto3 games
```

Canonical keys:

```text
mini loto6 loto7 bingo5 numbers3 numbers4
```

### Broad inventory

```bash
uv run loto3 catalog --counts
uv run loto3 catalog --library neuralforecast
```

The current broad inventory is 174 entries. It is a planning/inventory surface, not a success counter.

### Shared execution inventory

```bash
uv run loto models list --format table
```

This surface corresponds to `src/loto/models/catalog.py` and is narrower than the broad inventory.

### Unified development campaign

```bash
uv run loto3 campaign --output unused --plan-only

uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Every requested broad-catalog model × game pair receives a row. `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS` and `NON_STANDALONE_METHOD` are valid evidence states and are not hidden.

Primary metric is Hit@±1, accompanied by per-position/all-position Hit@±1, MAE, MSE and RMSE. Mandatory baselines and all configured seeds are retained. Predictions are sealed before the corresponding target actual is read for scoring.

## Current theory/evaluation additions

The current code base also includes:

- geometry-general outcome metrics for all six games;
- select/digit family-aware Hit@±1 decoding;
- exact IID-null theory reference and theory-aware target semantics;
- promotion policy v2 bound to sealed game identity and manual approval only;
- pre-experiment paired-score MDE/power planning with multiplicity adjustment.

These are implementation/planning/governance capabilities. They do not imply real-data superiority, Holdout completion or production promotion.

## Model surfaces

```text
catalog_full.py
  broad 174-entry inventory

catalog.py
  shared executable ModelSpec catalog

factory.py + workers.py
  shared candidate/position/foundation dispatch

models/providers/**
  shared foundation providers

*_campaign/** + adapters/** + environments/**
  isolated/provider-specific execution lanes

probabilistic/**
  separate 72-model probabilistic platform

audit/**
  point-in-time exact runtime evidence
```

Therefore:

```text
REGISTERED
!= IMPLEMENTED
!= SHARED_ROUTABLE / PROVIDER_ROUTABLE
!= RUNTIME_CERTIFIED
!= OOF_EVALUATED
!= HOLDOUT_EVALUATED
!= PROSPECTIVE_EVALUATED
!= PROMOTION_ELIGIBLE
```

## Document classes

### Live entry points / design contracts

These should be updated when current behavior changes:

- root `README.md`;
- `CAPABILITIES_AND_OPERATIONS.md`;
- this `docs/README.md`;
- `REQUIREMENTS.md`;
- `SPECIFICATION.md`;
- `ARCHITECTURE.md`;
- `DATA_CONTRACT.md`;
- `TEST_PLAN.md`;
- `CURRENT_RUNBOOK.md`;
- `UNIFIED_EVALUATION_CAMPAIGN.md`;
- `DOCUMENTATION_POLICY.md`.

### Audited snapshots

`STATUS.md`, `CURRENT_HANDOFF.md`, `CURRENT_VERIFICATION_REPORT.md`, `CURRENT_MODEL_EXECUTION_ADDENDUM.md`, and `CURRENT_ARTIFACT_MANIFEST.md` are timestamped snapshots. Live GitHub state wins after their `as_of` time.

### Generated inventory

`MODEL_INVENTORY.md` is generated. Do not hand-edit it to reflect routing or runtime results.

### Runtime/scientific evidence

Runtime certification applies to the exact model/revision/environment it actually exercised. OOF/Holdout/Prospective evidence applies only to the exact protocol/data/model identity that generated it.

### Historical evidence

Older root `VERIFICATION_REPORT.md`, prior handoffs and provider certification artifacts preserve their original observation. Add supersession guidance rather than rewriting historical facts.

### Immutable artifacts

Prediction/protocol locks, `SHA256SUMS`, model/data manifests and release bundles must not be silently regenerated in place.

## Scientific gate order

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
-> HUMAN APPROVAL
```

`champion=null` / `NO_MODEL_BEATS_BASELINE` are valid outcomes. Implementation completion does not open Holdout or Prospective.
