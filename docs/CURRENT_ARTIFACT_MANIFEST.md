# Current Documentation Artifact Manifest

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

This manifest identifies current live/control-plane documentation. It is not an experiment prediction manifest and does not replace per-run SHA-256 evidence.

| Artifact | Class | Purpose |
|---|---|---|
| `README.md` | LIVE_ENTRYPOINT | detailed project capability/model/library/operations guide |
| `docs/README.md` | LIVE_ENTRYPOINT | documentation authority/navigation map |
| `docs/CAPABILITIES_AND_OPERATIONS.md` | LIVE_REFERENCE | library/model/CLI/provider capability reference |
| `docs/STATUS.md` | AUDITED_SNAPSHOT | current repository/scientific boundary |
| `docs/REQUIREMENTS.md` | DESIGN_CONTRACT | platform/evaluation/governance requirements |
| `docs/SPECIFICATION.md` | DESIGN_CONTRACT | external executable/evidence contract |
| `docs/ARCHITECTURE.md` | DESIGN_CONTRACT | current model/evaluation/runtime/governance architecture |
| `docs/DATA_CONTRACT.md` | DESIGN_CONTRACT | immutable raw/chronology/split/data contract |
| `docs/TEST_PLAN.md` | DESIGN_CONTRACT | implementation/runtime/scientific/promotion test gates |
| `docs/MODEL_EXECUTION_MATRIX.md` | AUDITED_REFERENCE | detailed routing/runtime interpretation by library/model |
| `docs/UNIFIED_EVALUATION_CAMPAIGN.md` | DESIGN_CONTRACT | all-model × all-game development campaign |
| `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` | AUDITED_SNAPSHOT | current execution changes relative to earlier implementation stages |
| `docs/CURRENT_HANDOFF.md` | AUDITED_SNAPSHOT | next-engineer handoff |
| `docs/CURRENT_VERIFICATION_REPORT.md` | AUDITED_SNAPSHOT | current merge/CI/correctness evidence boundary |
| `docs/CURRENT_RUNBOOK.md` | DESIGN_CONTRACT | practical execution/verification procedure |
| `docs/DOCUMENTATION_POLICY.md` | DESIGN_CONTRACT | current/historical/generated/immutable interpretation rules |
| `CHANGELOG.md` | LIVE_ENTRYPOINT / HISTORY | notable repository changes |
| `VERIFICATION_REPORT.md` | HISTORICAL_EVIDENCE | preserved older verification snapshot |

## Generated / immutable evidence not rewritten

This documentation refresh deliberately does not hand-edit/regenerate:

- `docs/MODEL_INVENTORY.md` — generated broad model inventory;
- `audit/tsfm-runtime/**` — point-in-time runtime evidence;
- `configs/tsfm/verified-revisions.json` — verified revision mapping;
- historical provider-specific verification reports;
- sealed prediction/protocol artifacts;
- existing experiment/release `SHA256SUMS`.

## Current functional scope represented

Current docs reflect functional code through:

```text
#248 unified campaign
#249 WITHIN_TAU select decoder
#250 family-aware probability routing
#252 geometry-general metrics
#253 theory-aware promotion v2
#254 paired-score power/MDE planning
```

## SHA-256 handling

Mutable Markdown is versioned by Git commit/tree identity. Do not fabricate or overwrite experiment `SHA256SUMS` merely because documentation changed.

Cryptographic manifests remain attached to the immutable artifacts/runs they certify.

## Freshness

Live GitHub state and executable code/config win after this snapshot timestamp. Historical evidence remains historical and should be superseded by references rather than rewritten.
