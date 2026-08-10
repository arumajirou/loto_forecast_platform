# Documentation freshness and evidence policy

This policy prevents point-in-time operational facts from being mistaken for live repository state.

## 1. Documentation classes

Every operational document should be interpreted as one of these classes.

| Class | Purpose | May contain fixed dates/SHAs/run IDs? | Update rule |
|---|---|---:|---|
| `LIVE_ENTRYPOINT` | navigation and stable project contract | only as clearly labeled snapshot examples | keep aligned with current code and link to live checks |
| `AUDITED_SNAPSHOT` | point-in-time repository/project state | yes | never call itself auto-updating; record `as_of` and source |
| `DESIGN_CONTRACT` | requirements/specification/protocol | yes when part of immutable design identity | update when design changes; separate environment facts from protocol facts |
| `GENERATED_INVENTORY` | machine-derived counts/manifests | yes | regenerate from code; do not hand-edit |
| `HISTORICAL_EVIDENCE` | verification report, handoff, CI/run evidence | yes | preserve original evidence; add supersession banner rather than rewriting history |
| `IMMUTABLE_ARTIFACT` | SHA256SUMS, sealed prediction/protocol/evidence artifact | yes | never rewrite in place |

## 2. Canonical source precedence

When facts conflict:

1. live GitHub repository state for PR/Issue/branch/merge facts;
2. checked-in code/config for implementation and dependency contracts;
3. evidence bound to an exact SHA/run for executed behavior;
4. Linear for workflow tracking;
5. prose documentation for explanation and historical context.

No Markdown file may override a later GitHub merge state simply because it contains the word `current`.

## 3. Volatile facts

These facts must always include an `as_of` context or be replaced by a live-query instruction:

- main/head SHA;
- open PR/Issue counts;
- draft/mergeable/review state;
- latest Actions run ID or result;
- local workstation OS/tool availability;
- runner online/offline state;
- exact dependency availability on a host;
- local data/database presence;
- current scientific progress percentage;
- current champion/promotion state.

Do not encode workstation availability such as `LINUX_AVAILABLE=false` as a durable repository property.

## 4. Stable facts

Stable project contracts may be documented without a timestamp when they are backed by code/specification, for example:

- primary metric is Hit@±1;
- Holdout/Prospective separation rules;
- Train-only fitting of scalers/encoders/feature selection/HPO;
- prediction-before-actual SHA-256 sealing;
- `champion` may be null;
- runtime certification requires actual load/inference/device evidence;
- package version is derived dynamically rather than hand-written in README.

If code/specification changes these contracts, update the corresponding design document in the same PR.

## 5. Historical evidence preservation

Verification reports, handoffs, CI run IDs, exact model revisions, SHA-256 manifests and executed protocol artifacts are evidence for a specific time/identity.

When they become old:

- **do not rewrite their observed result**;
- add a banner such as `Historical snapshot — see ../STATUS.md for audited project state`;
- distinguish `captured_state` from `later_known_state`;
- never replace an old SHA/run ID with a new one inside an immutable evidence record.

This preserves reproducibility and auditability.

## 6. Generated facts

Generated inventories must identify their generator/source of truth.

Current examples:

- model counts: `loto3 catalog --counts` → `docs/MODEL_INVENTORY.md`;
- unified evaluation coverage: `loto3 campaign --plan-only` → requested broad-catalog × game matrix;
- unpinned TSFM revisions: `loto3 catalog --unpinned`;
- package version: `loto.version.__version__` / installed package metadata;
- integrity data: repository integrity command/artifacts.

README prose may summarize generated facts, but must link back to the generated source and label the value as a snapshot.

## 7. Scientific claims

Documentation must distinguish these levels:

1. Registered.
2. Dependency available.
3. Runtime loadable.
4. Inference verified.
5. OOF evaluated.
6. Holdout eligible/evaluated.
7. Promotion eligible/promoted.

A model appearing in a catalog is not a runtime or accuracy success. A complete unified campaign matrix means every requested pair has a terminal result row; it does not mean every pair executed successfully.

Formal forecast-quality claims require, at minimum:

- immutable data/split/protocol identity;
- leakage checks;
- required baselines under the same eligible folds;
- Hit@±1-first metric ordering;
- MAE/MSE/RMSE plus position/all-position Hit@±1;
- full configured seed inventory with mean/variance/worst;
- prediction sealing before actual access;
- runtime evidence where applicable.

Best-seed-only claims are not accepted.

## 8. Required metadata for status-like documents

A new status/handoff document should state:

```text
status_class=<AUDITED_SNAPSHOT|HISTORICAL_EVIDENCE|...>
as_of=<timestamp with timezone>
repository=<owner/name>
git_identity=<SHA or explicitly UNKNOWN/not applicable>
source_of_truth=<GitHub/code/evidence/...>
superseded_by=<path or NONE>
```

Human-readable prose is fine, but these semantics must be unambiguous.

## 9. Review checklist for documentation PRs

Before merge:

- [ ] re-fetch default branch/head and PR state;
- [ ] re-fetch open PRs/issues relevant to the document;
- [ ] compare generated counts with their generator/source;
- [ ] verify cited file paths exist;
- [ ] classify every fixed SHA/run/count as stable contract or point-in-time evidence;
- [ ] remove `latest/current` wording from run IDs unless a timestamp/source is attached;
- [ ] avoid workstation assumptions in portable design docs;
- [ ] preserve historical evidence instead of silently rewriting it;
- [ ] confirm no scientific status is promoted beyond executed evidence;
- [ ] inspect exact PR changed-file list and review threads;
- [ ] run/inspect the appropriate exact-head CI/documentation checks;
- [ ] merge with an expected-head guard when available.

## 10. Canonical entry points

Start with:

- [`../README.md`](../README.md) — stable project overview and usage;
- [`STATUS.md`](STATUS.md) — latest audited point-in-time state committed by the documentation process;
- [`README.md`](README.md) — documentation map;
- [`REQUIREMENTS.md`](REQUIREMENTS.md) — current Hit@±1-first platform requirements;
- [`SPECIFICATION.md`](SPECIFICATION.md) — current unified campaign/model-routing/decoder specification;
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current six-game evaluation/runtime architecture;
- [`DATA_CONTRACT.md`](DATA_CONTRACT.md) — immutable raw, chronology, split and prediction-data contract;
- [`TEST_PLAN.md`](TEST_PLAN.md) — current implementation/runtime/scientific test plan;
- [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md) — current handoff snapshot;
- [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) — current merge/CI verification snapshot;
- [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md) — current operational runbook;
- [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md) — merged all-model × all-game development campaign contract;
- [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md) — code-grounded routing/capability matrix;
- [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) — generated model inventory;
- [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) — scientific evaluation contract.
