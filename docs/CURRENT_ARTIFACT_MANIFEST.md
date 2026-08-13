# Current Documentation Artifact Manifest

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
```

This manifest identifies current live/control-plane documentation. It is not an experiment prediction manifest and does not replace per-run SHA-256 evidence.

| Artifact | Class | Purpose |
|---|---|---|
| `README.md` | LIVE_ENTRYPOINT | current implementation/evidence overview and navigation |
| `docs/README.md` | LIVE_ENTRYPOINT | documentation authority/navigation map and denominator guidance |
| `docs/CURRENT_CHANGE_SUMMARY.md` | AUDITED_CURRENT_STATE | concise major-change/history map tied to current evidence boundaries |
| `docs/CAPABILITIES_AND_OPERATIONS.md` | LIVE_REFERENCE | library/model/CLI/provider capability reference |
| `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md` | AUDITED_REFERENCE | detailed library/model inventory and capability table |
| `docs/STATUS.md` | AUDITED_CURRENT_STATE | current repository/scientific boundary and active gates |
| `docs/CURRENT_VERIFICATION_REPORT.md` | AUDITED_CURRENT_STATE | current correctness/evidence boundary |
| `docs/CURRENT_HANDOFF.md` | AUDITED_CURRENT_STATE | next-engineer handoff and priority gates |
| `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` | AUDITED_CURRENT_STATE | current execution changes/evidence classes layered over detailed matrices |
| `docs/darts/CURRENT_STATE_DARTS.md` | AUDITED_CURRENT_STATE | merged Darts foundation + local exact-worktree evidence boundary |
| `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` | OPERATOR_LOCAL_EVIDENCE | exact-source skforecast 0.23.0 maintainer-host runtime evidence and blockers |
| `docs/SKLEARN_ALL_MODELS.md` | LIVE_REFERENCE | dynamic all-estimator scikit-learn provider |
| `docs/PARALLEL_UNIFIED_CAMPAIGN.md` | LIVE_REFERENCE | game-parallel Broad campaign execution/live progress |
| `docs/LIGHTGBM_GPU_CERTIFICATION.md` | LIVE_REFERENCE | fail-closed LightGBM accelerator/backend certification |
| `docs/TSFM_RUNTIME_CAPABILITIES.md` | AUDITED_REFERENCE | retained TSFM identity/runtime interpretation |
| `docs/REQUIREMENTS.md` | DESIGN_CONTRACT | platform/evaluation/governance requirements |
| `docs/SPECIFICATION.md` | DESIGN_CONTRACT | external executable/evidence contract |
| `docs/ARCHITECTURE.md` | DESIGN_CONTRACT | model/evaluation/runtime/governance architecture |
| `docs/DATA_CONTRACT.md` | DESIGN_CONTRACT | immutable raw/chronology/split/data contract |
| `docs/TEST_PLAN.md` | DESIGN_CONTRACT | implementation/runtime/scientific/promotion test gates |
| `docs/MODEL_EXECUTION_MATRIX.md` | AUDITED_REFERENCE | detailed routing/runtime interpretation by library/model |
| `docs/UNIFIED_EVALUATION_CAMPAIGN.md` | DESIGN_CONTRACT | campaign/evaluation design; check current planner denominator before execution |
| `docs/CURRENT_RUNBOOK.md` | DESIGN_CONTRACT | practical execution/verification procedure |
| `docs/DOCUMENTATION_POLICY.md` | DESIGN_CONTRACT | current/historical/generated/immutable interpretation rules |
| `CHANGELOG.md` | LIVE_ENTRYPOINT / HISTORY | notable repository changes |
| `VERIFICATION_REPORT.md` | HISTORICAL_EVIDENCE | preserved older verification snapshot |

## Evidence-class rule

Current documentation must keep these distinct:

```text
CURRENT_CODE
REPOSITORY_RETAINED_EVIDENCE
EXACT_PR_SOURCE_EVIDENCE
OPERATOR_LOCAL_EVIDENCE
LOCAL_VERIFIED_MAIN_PENDING
SCIENTIFIC_EVALUATION_EVIDENCE
```

Examples:

- `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` records maintainer-host runtime evidence against exact source head `9fcc127...`; it does not close Expanded v2 #289 / TAJ-32.
- Draft PR #309 contains exact-head GluonTS CPU lifecycle evidence; until integrated it remains exact-PR evidence rather than current-main certification.
- Darts Torch/NLinear/DLinear local evidence is `LOCAL_VERIFIED / MAIN_PENDING`; current-main source-complete #286 / TAJ-27 work remains separate.

## Current denominator boundary

```text
Broad v1                           = 174
Probabilistic effective v1         = 76
Combined accounting                = 250
Current `loto3 campaign` plan      = 174 × 6 = 1,044
Combined accounting × six games    = 250 × 6 = 1,500
Expanded v2 Phase 1                = 210
```

The current single Broad campaign command does not automatically append the probabilistic 76 identities. Documentation/manifests must not use 1,500 as the current `loto3 campaign --plan-only` row count.

## Generated / immutable evidence not rewritten

Documentation refreshes do not hand-edit/regenerate:

- generated broad model inventories;
- `audit/tsfm-runtime/**` point-in-time runtime evidence;
- verified revision mappings;
- historical provider-specific verification reports;
- sealed prediction/protocol artifacts;
- experiment/release `SHA256SUMS`;
- the GluonTS PR #309 P7D archive merely to match a newer documentation commit.

## Current functional/documentation scope represented

Current docs cover the merged sequence through PR #313, including:

```text
#268 statistical/causal foundation
#270 runtime audit remediation
#273/#274/#276 repository observability/dashboard/control center
#277 scheduler stabilization
#293 Expanded v2 foundation
#295/#296 Toto 22M provenance/runtime infrastructure
#299/#300 documentation/library matrix
#301 dynamic sklearn provider
#302 parallel Broad campaign
#303 isotonic routing
#304 XGBoost/CatBoost GPU routing
#305/#306 LightGBM accelerator certification/routing
#307 sktime P1 normalization
#308 README current-state reconciliation
#310 current-state docs + skforecast operator evidence
#312 library/model matrix alignment
#311 Darts evidence + Broad planner boundary correction
#313 README audit-boundary stabilization
```

PR numbering does not guarantee merge chronology; current main/merge SHA is authoritative.

## SHA-256 handling

Mutable Markdown is versioned by Git commit/tree identity. Do not fabricate or overwrite experiment `SHA256SUMS` because documentation changed.

Cryptographic manifests remain attached to the immutable artifacts/runs they certify.

## Freshness

Live GitHub state and executable code/config win after this snapshot timestamp. Historical evidence remains historical and should be superseded by references rather than rewritten.
