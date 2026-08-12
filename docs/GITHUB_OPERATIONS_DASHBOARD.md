# GitHub Operations Dashboard

```text
status_class: LIVE_NAVIGATION_REFERENCE
repository: arumajirou/loto_forecast_platform
snapshot_main_sha: 775274cc22cf6701f148da80dfe86cb1bd099a7e
snapshot_at: 2026-08-12T14:06+09:00
```

This page is the human entry point for understanding the current state of the repository. Live GitHub state and run artifacts take precedence over this timestamped snapshot.

## 1. Where to look first

| Question | GitHub surface | Link / source |
|---|---|---|
| What is the overall certification progress? | Projects | [Loto Forecast — Runtime & Model Certification](https://github.com/users/arumajirou/projects/1) |
| What is currently blocked or planned? | Issues | [Open issues](https://github.com/arumajirou/loto_forecast_platform/issues?q=is%3Aissue%20state%3Aopen) |
| What is running or failing now? | Actions | [Actions](https://github.com/arumajirou/loto_forecast_platform/actions) |
| What changed in code? | Commits / Insights | [Commits](https://github.com/arumajirou/loto_forecast_platform/commits/main/) / [Insights](https://github.com/arumajirou/loto_forecast_platform/pulse) |
| What can the platform actually do? | Capability reference | [`docs/CAPABILITIES_AND_OPERATIONS.md`](CAPABILITIES_AND_OPERATIONS.md) |
| What is the audited scientific boundary? | Status | [`docs/STATUS.md`](STATUS.md) |
| What runtime campaign is authoritative? | Umbrella issue | [#269](https://github.com/arumajirou/loto_forecast_platform/issues/269) |
| What are the current scheduler defects? | Stabilization issue | [#271](https://github.com/arumajirou/loto_forecast_platform/issues/271) |
| Why does native Windows checkout fail? | Portability issue | [#272](https://github.com/arumajirou/loto_forecast_platform/issues/272) |

## 2. Current control-plane snapshot

| Item | Current state | Evidence boundary |
|---|---|---|
| Default branch | `main` | GitHub ref |
| Main SHA | `775274cc22cf6701f148da80dfe86cb1bd099a7e` | PR #270 merge |
| Open issues | 8 | live GitHub issue list at snapshot time |
| Active Actions workflows | 67 | live Actions workflow list at snapshot time |
| Repository Project | 1 open Project | user Project #1 |
| GitHub Pages | not configured at snapshot time | repository Pages endpoint returned no site |
| Broad canonical forecast identities | 174 | live planner/catalog contract |
| Probabilistic canonical identities | 76 | live planner/registry contract |
| Unified canonical identities | 250 | collision-free planner contract |
| Canonical games | 6 | `loto.game.geometry` |
| Broad matrix upper bound | 1,044 | 174 × 6 |
| Unified matrix upper bound | 1,500 | 250 × 6 |
| Holdout | CLOSED | scientific gate |
| Prospective | CLOSED | scientific gate |
| Automatic promotion | FORBIDDEN | promotion policy |

Do not interpret a catalog count as a runtime-success count. The capability ladder remains:

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

## 3. Open work by operational meaning

| Issue | Meaning | Current role |
|---|---|---|
| [#262](https://github.com/arumajirou/loto_forecast_platform/issues/262) | Runtime audit remediation umbrella | remains open until post-#270 stabilization is complete |
| [#269](https://github.com/arumajirou/loto_forecast_platform/issues/269) | All-model execution/certification umbrella | master runtime plan |
| [#265](https://github.com/arumajirou/loto_forecast_platform/issues/265) | Broad 174 × 6 | 1,044-unit runtime matrix |
| [#266](https://github.com/arumajirou/loto_forecast_platform/issues/266) | Unified 250 × 6 | 1,500-unit runtime matrix |
| [#271](https://github.com/arumajirou/loto_forecast_platform/issues/271) | Scheduler stabilization | resume integrity, GPU device assignment, timeout tree cleanup, outer cap |
| [#272](https://github.com/arumajirou/loto_forecast_platform/issues/272) | Windows portability | remove NTFS-invalid tracked paths |
| [#118](https://github.com/arumajirou/loto_forecast_platform/issues/118) | Timer-S1 | immutable runtime/certification gate |
| [#239](https://github.com/arumajirou/loto_forecast_platform/issues/239) | Timer Base 84M | leakage-safe OOF evaluation |

Completed weighted scheduler evidence is tracked in closed [#264](https://github.com/arumajirou/loto_forecast_platform/issues/264). The follow-up defects in #271 prevent treating the merged resource-aware foundation as final scheduler certification for every campaign topology.

## 4. Recommended Project views

The Project should expose the same data through several views rather than one overloaded table.

1. **00 Executive** — current phase, blockers, completion counts, latest run.
2. **01 Runtime Certification** — board grouped by runtime status.
3. **02 Model × Game Matrix** — table grouped by model/library and filtered by game.
4. **03 Accuracy Leaderboard** — development/OOF metrics only, sorted by Hit@±1 first.
5. **04 Failures & Blockers** — board grouped by normalized failure class.
6. **05 GPU / CPU** — resource class, device, peak VRAM/RSS, fallback state.
7. **06 Roadmap** — inventory → smoke → Broad → Unified → OOF → Holdout → Prospective.
8. **07 Formal Gates** — Holdout/Prospective/promotion state; development runs must not open these gates.

The exact field definitions are in [`GITHUB_PROJECT_SCHEMA.md`](GITHUB_PROJECT_SCHEMA.md).

## 5. Actions usage rule

The Actions tab currently contains many specialized workflows. Use this hierarchy when reading it:

1. `00 / repository observability dashboard` — repository-level navigation/status summary.
2. `ci` — canonical repository test gate.
3. named runtime/certification workflows — model/provider-specific evidence.
4. historical repair/diagnostic workflows — evidence/debug only; do not treat their existence as a current production path.

Each new certification/evaluation workflow should publish a concise `$GITHUB_STEP_SUMMARY` containing, where applicable:

- Run ID and Git SHA;
- model ID / revision and game;
- requested/effective device;
- load/inference/output shape/finite verdict;
- GPU PID / peak VRAM or CPU fallback classification;
- primary Hit@±1 and companion metrics when scientific scoring is authorized;
- mandatory baseline comparison;
- prediction-lock SHA-256 state;
- normalized final status and failure class;
- Holdout / Prospective / promotion boundary.

## 6. Source-of-truth priority

When information disagrees, use this order:

1. live GitHub ref / issue / PR / Actions state;
2. immutable run artifacts and SHA-256 manifests;
3. current code/config at the exact Git SHA;
4. generated status/dashboard snapshot;
5. prose documentation.

A dashboard is navigation, not scientific evidence.

## 7. Next GitHub UX improvements

- Consolidate or explicitly classify the 67 active workflows before disabling anything; do not delete evidence workflows merely to reduce visual clutter.
- Enable GitHub Pages only after a reviewed dashboard publish workflow exists; use it for interactive Model × Game heatmaps and metric/resource plots.
- Keep Project items at Model × Game / work-item granularity. Keep seed/fold/trial detail in artifacts/registry rather than creating thousands of Project cards.
- Use Issues for actionable blockers and scientific work, not as a row-per-run database.
- Use Releases for immutable certification snapshots once a campaign is formally accepted.
