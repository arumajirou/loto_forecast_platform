# GitHub Operations Dashboard

```text
status_class: LIVE_NAVIGATION_REFERENCE
repository: arumajirou/loto_forecast_platform
snapshot_main_sha: c57731e17b43f8f5d9e038c75017aa9ce83fd5e9
snapshot_at: 2026-08-12T15:51+09:00
```

This page is the human control center for the repository. Live GitHub refs, Issues, Pull Requests,
Actions and immutable run artifacts take precedence over this timestamped snapshot.

## 1. Start here

| Question | Primary surface | Link / source |
|---|---|---|
| What is the overall certification progress? | Project | [Loto Forecast — Runtime & Model Certification](https://github.com/users/arumajirou/projects/1) |
| What is blocked or planned? | Issues | [Open Issues](https://github.com/arumajirou/loto_forecast_platform/issues?q=is%3Aissue+state%3Aopen) |
| What is running or failing now? | Actions | [Actions](https://github.com/arumajirou/loto_forecast_platform/actions) |
| What is the repository-level status summary? | Actions summary | [`00 / repository observability dashboard`](https://github.com/arumajirou/loto_forecast_platform/actions/workflows/github-observability-dashboard.yml) |
| Can I inspect the visual Model × Game dashboard artifact? | Visual build | [`00 / visual dashboard build`](https://github.com/arumajirou/loto_forecast_platform/actions/workflows/github-visual-dashboard-build.yml) |
| Why is the visual dashboard not public yet? | Pages activation | [#275](https://github.com/arumajirou/loto_forecast_platform/issues/275) |
| What runtime campaign is authoritative? | Runtime umbrella | [#269](https://github.com/arumajirou/loto_forecast_platform/issues/269) |
| What are the scheduler defects? | Stabilization | [#271](https://github.com/arumajirou/loto_forecast_platform/issues/271) |
| Why does native Windows checkout fail? | Portability | [#272](https://github.com/arumajirou/loto_forecast_platform/issues/272) |
| What can the platform actually do? | Capability reference | [`CAPABILITIES_AND_OPERATIONS.md`](CAPABILITIES_AND_OPERATIONS.md) |
| What is the audited scientific boundary? | Scientific status | [`STATUS.md`](STATUS.md) |

## 2. Current control-plane snapshot

| Item | Snapshot state | Authority |
|---|---|---|
| Default branch | `main` | live GitHub ref |
| Main SHA | `c57731e17b43f8f5d9e038c75017aa9ce83fd5e9` | PR #274 merge |
| Open Issues | 9 | live GitHub issue search |
| Actions workflows returned by API | 71 total | live Actions workflow API |
| Repository Project | Project #1 | GitHub Projects |
| Visual dashboard build | IMPLEMENTED / VERIFIED | PR #274 + Actions artifacts |
| GitHub Pages site | BLOCKED / NOT LIVE | Pages endpoint 404; #275 |
| Broad canonical identities | 174 | live planner/catalog contract |
| Probabilistic canonical identities | 76 | live planner/registry contract |
| Unified canonical identities | 250 | collision-free planner contract |
| Canonical games | 6 | `loto.game.geometry` |
| Broad planning matrix | 1,044 | 174 × 6 |
| Unified planning matrix | 1,500 | 250 × 6 |
| Current visual-dashboard cells | 1,500 `UNASSESSED` by default | fail-closed dashboard contract |
| Holdout | CLOSED | scientific gate |
| Prospective | CLOSED | scientific gate |
| Automatic promotion | FORBIDDEN | promotion policy |

Do not interpret inventory or dashboard cells as runtime-success counts. The capability ladder remains:

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
-> HUMAN APPROVAL
```

## 3. Current work by operational meaning

| Issue | Meaning | Current role |
|---|---|---|
| [#262](https://github.com/arumajirou/loto_forecast_platform/issues/262) | Runtime remediation umbrella | remains open until scheduler/runtime stabilization closes |
| [#269](https://github.com/arumajirou/loto_forecast_platform/issues/269) | All-model execution/certification umbrella | master runtime plan |
| [#265](https://github.com/arumajirou/loto_forecast_platform/issues/265) | Broad 174 × 6 | 1,044-unit runtime matrix |
| [#266](https://github.com/arumajirou/loto_forecast_platform/issues/266) | Unified 250 × 6 | 1,500-unit runtime matrix |
| [#271](https://github.com/arumajirou/loto_forecast_platform/issues/271) | Scheduler stabilization | resume integrity, GPU assignment, timeout trees, outer cap |
| [#272](https://github.com/arumajirou/loto_forecast_platform/issues/272) | Windows portability | remove NTFS-invalid tracked paths |
| [#275](https://github.com/arumajirou/loto_forecast_platform/issues/275) | GitHub Pages activation | repository setting is the remaining publish gate |
| [#118](https://github.com/arumajirou/loto_forecast_platform/issues/118) | Timer-S1 | immutable runtime/certification gate |
| [#239](https://github.com/arumajirou/loto_forecast_platform/issues/239) | Timer Base 84M | leakage-safe OOF evaluation |

Closed #264 contains weighted-scheduler evidence. PR #274 contains the visual-dashboard foundation. Neither
closes #271/#272 or upgrades runtime/accuracy certification by implication.

## 4. Visual dashboard status

PR #274 added an evidence-aware static dashboard and a fail-closed build workflow.

Verified foundation:

```text
canonical identities: 250
canonical games:       6
planning cells:        1500
default status:        UNASSESSED
Holdout:               CLOSED
Prospective:           CLOSED
automatic promotion:   FORBIDDEN
```

The build workflow may create a verified artifact without publishing a public site. Public deployment remains
blocked until repository Pages is explicitly configured to use **GitHub Actions** as the publishing source.
Track that activation only in #275. Do not report a Pages URL as live while the Pages endpoint returns 404.

## 5. Recommended Project views

Use one Project with several views rather than one overloaded table:

1. **00 Executive** — phase, blockers, completion counts, latest evidence.
2. **01 Runtime Certification** — board grouped by runtime status.
3. **02 Model × Game Matrix** — model/library × game work items.
4. **03 Accuracy Leaderboard** — development/OOF only, Hit@±1 first.
5. **04 Failures & Blockers** — normalized failure class.
6. **05 GPU / CPU** — resource class, requested/effective device, VRAM/RSS, fallback.
7. **06 Roadmap** — inventory → smoke → Broad → Unified → OOF → Holdout → Prospective.
8. **07 Formal Gates** — Holdout/Prospective/promotion state.

Exact field definitions remain in [`GITHUB_PROJECT_SCHEMA.md`](GITHUB_PROJECT_SCHEMA.md).

## 6. Actions reading order

The Actions API currently exposes many historical and specialized workflows. Use this hierarchy:

1. `00 / repository observability dashboard` — navigation/control-plane summary.
2. `00 / visual dashboard build` — verified visual artifact and future Pages deployment gate.
3. `ci` — canonical repository test gate.
4. named runtime/certification workflows — provider/model evidence.
5. historical repair/diagnostic workflows — evidence/debug only.

Do not disable workflows merely to make the Actions list shorter. Consolidation requires a separate audit that proves
whether each workflow is canonical, provider-specific, historical evidence, one-shot repair, or safe to retire.

## 7. Source-of-truth priority

When information disagrees, use this order:

1. live GitHub ref / Issue / PR / Actions / Pages state;
2. immutable run artifacts and SHA-256 manifests;
3. current code/config at the exact Git SHA;
4. generated dashboard/status snapshot;
5. prose documentation.

A dashboard is navigation and observability, not scientific evidence.

## 8. Immediate GitHub UX priorities

1. Activate Pages only when #275 repository enablement is available; then verify the deployed artifact byte-for-byte.
2. Classify the 71 returned Actions workflows before retiring any of them.
3. Keep Project items at Model × Game / actionable-work granularity; retain seed/fold/trial detail in run artifacts.
4. Keep Issues for blockers and work packages rather than one Issue per run.
5. Use Releases only for immutable, formally accepted certification snapshots.
6. Keep #271 and #272 visibly separate from dashboard success so infrastructure debt cannot disappear behind green UI.
