# Documentation freshness and evidence policy

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

This policy prevents point-in-time operational facts, catalog registrations and scientific claims from being mistaken for one another.

## 1. Documentation classes

| Class | Purpose | Fixed dates/SHAs/run IDs | Update rule |
|---|---|---:|---|
| `LIVE_ENTRYPOINT` | navigation/current usage | only when clearly labeled | keep aligned with current code |
| `LIVE_REFERENCE` | detailed current operational reference | yes as audit base | update with relevant code changes |
| `AUDITED_SNAPSHOT` | point-in-time repository/project state | yes | include `as_of` and evidence source |
| `DESIGN_CONTRACT` | requirements/specification/protocol | yes when identity matters | update when contract changes |
| `GENERATED_INVENTORY` | machine-derived counts/manifests | yes | regenerate; do not hand-edit |
| `HISTORICAL_EVIDENCE` | old verification/handoff/CI evidence | yes | preserve observed result; supersede by link |
| `IMMUTABLE_ARTIFACT` | prediction/protocol/hash/release evidence | yes | never rewrite in place |

## 2. Source precedence

When facts conflict:

1. live GitHub state for PR/Issue/branch/merge facts;
2. checked-in executable code/config for implementation/dependency contracts;
3. evidence bound to an exact SHA/run/model/data identity for executed behavior;
4. generated inventory for generated counts;
5. workflow tracker such as Linear for planning state;
6. prose documentation for explanation/context.

No Markdown file overrides later live GitHub state merely by saying `current`.

## 3. Volatile facts

These require `as_of` or a live-query instruction:

- main/head SHA;
- open PR/Issue counts;
- draft/mergeable/review state;
- Actions run result;
- runner online state;
- workstation/GPU availability;
- local data/database presence;
- dependency availability on a specific machine;
- current champion/promotion state;
- scientific progress percentages.

## 4. Stable project contracts

Examples that may be stated without a volatile timestamp when backed by current code/spec:

- six canonical game keys/geometry source;
- Hit@±1 is primary evaluation metric;
- Train-only fitting for learned preprocessing/search components;
- prediction-before-actual sealing;
- best-seed-only selection is forbidden;
- runtime certification requires actual execution evidence;
- automatic promotion/retraining/registry writes are forbidden by current promotion policy models;
- package version is derived rather than hard-coded in README.

If the implementation changes a stable contract, update the design documents in the same PR.

## 5. Model capability taxonomy

Documentation must not use a single ambiguous `available` label for all model states.

Use these stages where relevant:

```text
REGISTERED
DEPENDENCY_DECLARED
IMPLEMENTED
SHARED_ROUTABLE
PROVIDER_ROUTABLE
RUNTIME_CERTIFIED
LOTTERY_COMPATIBLE
OOF_EVALUATED
HOLDOUT_EVALUATED
PROSPECTIVE_EVALUATED
PROMOTION_ELIGIBLE
HUMAN_APPROVED / PROMOTED
```

Examples:

- 174 broad forecast entries = `REGISTERED` planning inventory, not 174 shared successes.
- 72 probabilistic catalog entries = separate registered/implemented probabilistic surface, not 72 formal OOF winners.
- TSFM runtime-certified evidence = exact runtime identity evidence, not forecast-quality evidence.

## 6. Historical evidence preservation

When old verification reports, handoffs, CI runs or model revisions become stale:

- do not rewrite the observed result;
- add supersession/current-reference guidance where needed;
- distinguish captured state from later-known state;
- never replace an old SHA/run/model identity inside immutable evidence.

## 7. Generated facts

Examples:

```text
uv run loto3 catalog --counts
  -> broad model counts

uv run loto3 campaign --output unused --plan-only
  -> requested model × game coverage plan

uv run loto3 catalog --unpinned
  -> broad TSFM entries needing explicit revision binding

loto.version.__version__ / package metadata
  -> package version
```

`docs/MODEL_INVENTORY.md` is generated. Do not edit it by hand to represent routing, certification or OOF progress.

## 8. Runtime claims

A runtime claim should identify the exact model/repo/revision/environment and applicable evidence for load, inference, output shape/finite values, effective device, fallback and reload.

`dependency installed` or `class importable` is a weaker claim.

If a provider is CPU-pinned, do not describe registration as CUDA support.

## 9. Scientific claims

Formal forecast-quality claims require at least applicable:

- immutable data/split/protocol identity;
- leakage checks;
- mandatory baselines under the same eligible folds;
- Hit@±1-first metric interpretation;
- MAE/MSE/RMSE and position/all-position Hit@±1;
- full configured seed inventory and variance/worst statistics;
- prediction sealing before actual access;
- model/runtime identity;
- explicit failure retention.

`matrix_complete` means every requested pair has a result row, not that every result is success.

## 10. Theory claims

When quoting an IID-null ceiling/reference:

- identify game and tau;
- state that it is exact under the specified IID-null distribution;
- do not call it a universal bound for every possible biased process;
- distinguish an absolute target from excess-vs-null target semantics;
- require explicit alternative-hypothesis semantics when the code guard requires it.

## 11. Power/MDE claims

Pre-experiment MDE/power output must be labeled planning evidence.

Record method identity and assumptions. `score_sd` must be fixed from allowed pre-target evidence or declared simulation. Do not call planning output a realized p-value, Holdout result or promotion result.

## 12. Promotion claims

Distinguish:

```text
NOT_ELIGIBLE
ELIGIBLE_FOR_HUMAN_APPROVAL
HUMAN_APPROVED
PROMOTED
```

Current automatic rules may only establish eligibility. They do not authorize production mutation.

Never rewrite historical v1 promotion evidence as v2 simply to apply newer semantics.

## 13. Required metadata for status-like documents

Recommended:

```text
status_class=<...>
as_of=<timestamp with timezone>
repository=<owner/name>
code_audit_base_sha=<SHA or UNKNOWN>
source_of_truth=<...>
```

For a documentation-only refresh, `code_audit_base_sha` may identify the functional code state that was inspected even though the documentation commit itself will have a later SHA.

## 14. Documentation PR checklist

Before merge:

- [ ] re-fetch default branch/head and PR state;
- [ ] re-fetch relevant open PRs/issues;
- [ ] compare broad/generated counts with executable source;
- [ ] distinguish shared and isolated providers;
- [ ] verify cited file paths/commands;
- [ ] classify every fixed SHA/run/count;
- [ ] preserve generated and immutable evidence;
- [ ] do not promote scientific status beyond executed evidence;
- [ ] inspect exact changed-file list;
- [ ] inspect review threads/submissions;
- [ ] run/inspect exact-head/current-base CI;
- [ ] re-check main/head race before merge;
- [ ] merge with expected-head guard.

## 15. Canonical entry points

- [`../README.md`](../README.md) — detailed project capability/usage guide;
- [`CAPABILITIES_AND_OPERATIONS.md`](CAPABILITIES_AND_OPERATIONS.md) — model/library/CLI/provider reference;
- [`STATUS.md`](STATUS.md) — latest audited repository/scientific snapshot;
- [`README.md`](README.md) — documentation map;
- [`MODEL_EXECUTION_MATRIX.md`](MODEL_EXECUTION_MATRIX.md) — code-grounded routing/capability matrix;
- [`UNIFIED_EVALUATION_CAMPAIGN.md`](UNIFIED_EVALUATION_CAMPAIGN.md) — canonical broad development campaign;
- [`REQUIREMENTS.md`](REQUIREMENTS.md), [`SPECIFICATION.md`](SPECIFICATION.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_CONTRACT.md`](DATA_CONTRACT.md), [`TEST_PLAN.md`](TEST_PLAN.md) — design contracts;
- [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md), [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md), [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) — current operating snapshots;
- [`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) — generated inventory;
- [`evaluation_protocol/PROTOCOL_V2.md`](evaluation_protocol/PROTOCOL_V2.md) — scientific evaluation contract.
