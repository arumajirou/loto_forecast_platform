# Repository status snapshot

> **Status class:** audited point-in-time snapshot, not an auto-updating dashboard  
> **Verified at:** 2026-08-10 16:24 JST  
> **Repository:** `arumajirou/loto_forecast_platform`  
> **Audit base:** `main@0bb4680b2d26cfd32788381f580d86a4acd0fb6d`

This document answers “what was actually true when the documentation audit was performed?” without turning volatile GitHub, CI, workstation, or Linear state into permanent repository constants.

For rules on freshness and historical evidence, read [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md).

## 1. Source-of-truth order

When documents disagree, use this precedence:

1. **Live GitHub state** for branch, PR, Issue, review and merge state.
2. **Versioned repository code/config** for implemented behavior and dependency contracts.
3. **Exact-SHA CI/runtime evidence** for what was actually executed and verified.
4. **Linear** for work tracking; GitHub remains authoritative for repository state.
5. **Point-in-time documentation** for historical context only.

A document saying “current” does not override a later GitHub state.

## 2. GitHub state verified during this audit

| Item | Verified state |
|---|---|
| default branch | `main` |
| main HEAD at audit start | `0bb4680b2d26cfd32788381f580d86a4acd0fb6d` |
| latest merged change at audit start | PR #240, `feat(timer): add leakage-safe OOF evaluation` |
| PR #240 | merged; merge SHA `0bb4680b2d26cfd32788381f580d86a4acd0fb6d` |
| open PRs | exactly one: PR #245 (documentation refresh) |
| open GitHub Issues | #239 and #118 |
| repository permissions of connected maintainer | admin / maintain / push / triage available |
| repository visibility | private |

Recent merged work immediately preceding this audit includes:

- #240 — Timer Base 84M leakage-safe OOF evaluation foundation;
- #238 — Timer Base 84M pinned snapshot/runtime certification;
- #237 — AutoGluon protocol-v2/shared worker integration;
- #235 — standard Linux CI migrated to the self-hosted runner;
- #234/#233/#232/#230/#229 — provider/runtime/test contract repairs.

This materially supersedes older project summaries that still describe large Open-PR queues, 929 Ruff findings, 34 pytest collection errors, or 52 full-pytest execution failures as current. Those were valid intermediate states but have since been remediated and merged.

## 3. Linear state verified during this audit

Linear team: `Tajimaharu`.

| Issue | State | Interpretation |
|---|---|---|
| TAJ-12 | In Progress | Timer Base 84M OOF scientific work remains open |
| TAJ-11 | Done | Timer Base 84M repository verification/runtime certification work completed |
| TAJ-10 | Done | 52 full-pytest execution failures remediation completed |
| TAJ-9 | Done | standard CI self-hosted Linux migration completed |
| TAJ-8 | Done | pytest collection debt remediation completed |
| TAJ-7 | Done | Ruff lint debt remediation completed |
| TAJ-5 / TAJ-6 | Done | formatting and invalid UTF-8 blockers completed |
| TAJ-13 | In Progress during this audit | repository-wide documentation alignment |

Linear descriptions may contain the GitHub baseline from the moment an issue was created. They must not be used as a substitute for re-fetching GitHub before a merge, release, or scientific run.

## 4. Scientific status

The merge of PR #240 completed the **engineering foundation**, not the forecast-quality experiment.

The scientific boundary preserved by PR #240 at merge time is:

```text
scientific_progress=18%
formal_oof_run=false
timer_inference_run=false
holdout_actuals_opened=false
prospective_actuals_opened=false
accuracy_claim=false
champion_claim=false
promotion=false
```

Therefore:

- there is no verified Timer Base 84M OOF accuracy result yet;
- there is no champion/promotion claim;
- Holdout and Prospective remain closed;
- a valid future result may still be `NO_MODEL_BEATS_BASELINE` / `champion=null`.

Primary metric remains `Hit@±1`. Required companion metrics are MAE, MSE, RMSE, position Hit@±1 and all-position Hit@±1. Formal comparisons retain all configured seeds and report mean, variance and worst values.

## 5. Model inventory

[`MODEL_INVENTORY.md`](MODEL_INVENTORY.md) is generated and explicitly identifies `loto3 catalog --counts` as the source of truth.

At this audit snapshot it records:

- 174 registered estimators total;
- NeuralForecast fixed models: 37;
- NeuralForecast AutoModels: 36;
- StatsForecast: 41;
- MLForecast Auto: 8;
- HierarchicalForecast reconciliation methods: 10;
- TSFM registrations: 21;
- all 21 TSFM revisions recorded there as `UNPINNED` until formal fixation.

Registration is **Level 1 only**. It is not equivalent to dependency availability, runtime loading, inference verification, OOF evaluation, Holdout eligibility, or promotion eligibility.

## 6. Dependency/config facts

`pyproject.toml` uses dynamic package versioning from `loto.version.__version__`; the README must not hand-maintain a package version.

At the audit base, notable root dependencies include:

- Python `>=3.11,<3.14`;
- `neuralforecast==3.2.0`;
- `torch==2.9.1`;
- `transformers==4.57.6`;
- `huggingface-hub==0.36.2`;
- optional groups for `auto-campaign`, `api`, `mlflow`, `postgres`, `full`, `frameworks`, and `tsfm`.

Always inspect the committed `pyproject.toml` and `uv.lock` rather than copying version values from an old tutorial.

## 7. CI/runtime evidence boundary

CI and runtime claims are valid only for the exact SHA/run on which they were observed.

Verified historical/currently-relevant evidence includes:

- standard Linux CI was migrated to the self-hosted lane by PR #235; its PR-head standard CI completed all intended steps successfully;
- native Windows portability was merged by PR #194 and was also exercised during the PR #240 work;
- PR #240 recorded 20/20 focused Windows validation and successful Windows portability evidence on its pre-merge head;
- the GitHub connector exposed no combined commit-status records on merge commit `0bb4680...` during this audit, so this document does **not** invent a merge-commit CI result.

A workstation being available or unavailable is session-specific. It is **not** a durable repository property. Windows-only or Linux-only statements in older handoff bundles are historical execution context unless re-verified for the current session.

## 8. What was stale and how to read it now

The following patterns are explicitly treated as historical unless re-verified:

- `PR_240_STATE=open/draft` — superseded; PR #240 is merged.
- `CURRENT_OPERATOR_ENVIRONMENT=native Windows only` — session-specific, not a repository invariant.
- old Ruff/pytest debt counts — superseded by later remediation PRs and completed Linear issues.
- old Open PR/Issue totals — point-in-time only.
- fixed CI run IDs described as “latest” — evidence for those exact runs only.
- old model counts in prose — use generated inventory / CLI instead.

Historical verification reports, SHA-256 manifests, changelogs and handoffs should normally **not** be rewritten merely because the project advanced; their status scope must instead be made explicit.

## 9. Live verification commands

For a maintainer with `gh` access:

```bash
gh repo view arumajirou/loto_forecast_platform --json defaultBranchRef
gh pr list -R arumajirou/loto_forecast_platform --state open
gh issue list -R arumajirou/loto_forecast_platform --state open
gh run list -R arumajirou/loto_forecast_platform --limit 20
```

Repository-derived model/config checks:

```bash
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 catalog --unpinned
uv run loto3 integrity check
```

Before any formal scientific run, additionally record exact Git commit, clean-tree state, data/split/feature hashes, protocol hash, package/runtime identity, resource measurements and prediction seals.

## 10. Next repository/scientific work after this snapshot

Repository documentation work is tracked by PR #245 / TAJ-13.

Scientific work remains tracked by GitHub Issue #239 / Linear TAJ-12. The next scientific step is still leakage-safe Timer Base 84M OOF preparation/execution under the fixed protocol. Holdout and Prospective remain closed until their later gates are explicitly authorized.
