# Data Contracts

## Status

`CURRENT`

This document defines repository-wide data-governance rules. Feature-specific schemas may add fields and stronger validation, but they must preserve the temporal and immutability rules below.

## 1. Raw source authority

Raw source data is an immutable evidence layer.

- Do not overwrite previously captured Raw data in place.
- Corrections create a new data/versioned artifact with explicit provenance.
- Preserve enough source identity to reproduce which bytes/records were used by a run.
- Derived/normalized datasets must point back to their source snapshot/version.

## 2. Time semantics

Event time and information-availability time are distinct concepts.

Typical draw-level records include identifiers such as:

```text
draw_id, draw_no, draw_date, ..., available_at
```

`available_at` represents when the information was eligible to be used by a forecasting process. An external variable whose availability time cannot be established for the prediction boundary is prohibited from formal leakage-safe evaluation until that provenance is resolved.

## 3. Example logical tables

Actual physical schemas differ by game/family, but common logical views include:

### Draw master

```text
draw_id, draw_no, draw_date, positions..., bonus..., available_at
```

### Position view

```text
draw_id, draw_no, draw_date, position, value, available_at
```

### Candidate/inclusion view

```text
draw_id, draw_no, draw_date, candidate, selected, position_if_selected, available_at
```

### Feature view

Feature rows must carry enough identity to prove which historical boundary produced them. Rolling/frequency/gap features must be computed from information available strictly before the target prediction boundary.

## 4. Versioning and provenance

Formal datasets/artifacts should record, as applicable:

- schema version;
- data snapshot/version identity;
- source/provenance identity;
- content hash such as SHA-256;
- extraction/canonicalization configuration;
- availability-time policy;
- code/config identity used to derive the artifact.

A model/run identifier does not replace a data snapshot identifier.

## 5. Train/evaluation boundary

Train, Validation/OOF, Holdout, and Prospective are chronological boundaries.

Scalers, encoders, feature selection, hyperparameter search, and learned preprocessing may only use the data permitted by the active training/development boundary. Holdout/Prospective data must not be imported into those fitting decisions.

## 6. Data-quality and leakage gates

Formal pipelines should detect or explicitly classify:

- duplicate observations/keys;
- missing required values;
- ordering violations;
- impossible/range-invalid values;
- future-information contamination;
- missing/ambiguous `available_at` evidence;
- unintended overlap between chronological partitions.

A detected issue is not silently repaired across a temporal boundary. Remediation must produce an auditable new artifact/version.

## 7. Prospective actuals

Prospective prediction artifacts are locked before actual outcomes are introduced. Actual-bearing artifacts are separate evidence and must not be present in the prediction-lock input before the lock timestamp.

`src/loto/auto_campaign/prediction_lock.py` enforces the prospective lock's `actual_known=false`/actual-artifact boundary for the campaign path.

## 8. Storage

Physical representations may include JSON, CSV, Parquet, relational databases, or artifact stores. Storage choice does not weaken the logical data contract, immutability requirements, or temporal provenance rules.

Raw/source evidence and derived operational tables have different mutation semantics; mutable operational state must not be used as a substitute for immutable Raw evidence.
