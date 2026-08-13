# Current Documentation Artifact Manifest

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T17:36+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
```

This manifest identifies current live/control-plane documentation. It is not an experiment prediction manifest and does not replace per-run SHA-256 evidence.

| Artifact | Class | Purpose |
|---|---|---|
| `README.md` | LIVE_ENTRYPOINT | current implementation/evidence overview and navigation |
| `docs/README.md` | LIVE_ENTRYPOINT | documentation authority/navigation map |
| `docs/CAPABILITIES_AND_OPERATIONS.md` | LIVE_REFERENCE | library/model/CLI/provider capability reference |
| `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md` | AUDITED_REFERENCE | detailed library/model inventory and capability table; runtime-specific later evidence may be superseded by current addenda |
| `docs/STATUS.md` | AUDITED_CURRENT_STATE | current repository/scientific boundary and active gates |
| `docs/CURRENT_VERIFICATION_REPORT.md` | AUDITED_CURRENT_STATE | current correctness/evidence boundary |
| `docs/CURRENT_HANDOFF.md` | AUDITED_CURRENT_STATE | next-engineer handoff and priority gates |
| `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` | AUDITED_CURRENT_STATE | execution changes layered over detailed matrices |
| `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` | OPERATOR_LOCAL_EVIDENCE | exact-source skforecast 0.23.0 maintainer-host runtime evidence and blockers |
| `docs/SKLEARN_ALL_MODELS.md` | LIVE_REFERENCE | dynamic all-estimator scikit-learn provider |
| `docs/PARALLEL_UNIFIED_CAMPAIGN.md` | LIVE_REFERENCE | game-parallel campaign execution/live progress |
| `docs/LIGHTGBM_GPU_CERTIFICATION.md` | LIVE_REFERENCE | fail-closed LightGBM accelerator/backend certification |
| `docs/TSFM_RUNTIME_CAPABILITIES.md` | AUDITED_REFERENCE | retained TSFM identity/runtime interpretation |
| `docs/REQUIREMENTS.md` | DESIGN_CONTRACT | platform/evaluation/governance requirements |
| `docs/SPECIFICATION.md` | DESIGN_CONTRACT | external executable/evidence contract |
| `docs/ARCHITECTURE.md` | DESIGN_CONTRACT | model/evaluation/runtime/governance architecture |
| `docs/DATA_CONTRACT.md` | DESIGN_CONTRACT | immutable raw/chronology/split/data contract |
| `docs/TEST_PLAN.md` | DESIGN_CONTRACT | implementation/runtime/scientific/promotion test gates |
| `docs/MODEL_EXECUTION_MATRIX.md` | AUDITED_REFERENCE | detailed routing/runtime interpretation by library/model |
| `docs/UNIFIED_EVALUATION_CAMPAIGN.md` | DESIGN_CONTRACT | all-model × all-game development campaign |
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
SCIENTIFIC_EVALUATION_EVIDENCE
```

In particular, `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` records maintainer-host runtime evidence against source head `9fcc127...`; it does not by itself certify the newer merged main SHA or close Expanded v2 #289 / TAJ-32.

## Generated / immutable evidence not rewritten

Documentation refreshes do not hand-edit/regenerate:

- generated broad model inventories;
- `audit/tsfm-runtime/**` point-in-time runtime evidence;
- verified revision mappings;
- historical provider-specific verification reports;
- sealed prediction/protocol artifacts;
- experiment/release `SHA256SUMS`.

## Current functional scope represented

Current docs cover the merged sequence through PR #308, including:

```text
#268 statistical/causal foundation
#270 runtime audit remediation
#273/#274/#276 repository observability/dashboard/control center
#277 scheduler stabilization
#293 Expanded v2 foundation
#295/#296 Toto 22M provenance/runtime infrastructure
#299/#300 documentation/library matrix
#301 dynamic sklearn provider
#302 parallel campaign
#303 isotonic routing
#304 XGBoost/CatBoost GPU routing
#305/#306 LightGBM accelerator certification/routing
#307 sktime P1 normalization
#308 README current-state reconciliation
```

The 2026-08-13 skforecast maintainer-host sequence is documented as a separate operator-local evidence class rather than inserted into historical immutable runtime artifacts.

## SHA-256 handling

Mutable Markdown is versioned by Git commit/tree identity. Do not fabricate or overwrite experiment `SHA256SUMS` merely because documentation changed.

Cryptographic manifests remain attached to the immutable artifacts/runs they certify.

## Freshness

Live GitHub state and executable code/config win after this snapshot timestamp. Historical evidence remains historical and should be superseded by references rather than rewritten.
