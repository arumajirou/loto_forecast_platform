# MLForecast architecture

## Component map

```text
CSV / Parquet source
        |
        v
contracts.py ---- strict Pydantic configuration
        |
        v
data.py -------- canonical schema, ordering, leakage checks, future keys
        |
        +------------------------+
        |                        |
        v                        v
factory.py                 metrics.py
Core / Auto construction   Hit@±1-first objective and baselines
        |                        |
        +-----------+------------+
                    v
runner.py ---------- Train/Holdout/Prospective lifecycle
                    |
                    v
runtime.py -------- save/load/re-predict and finite/shape checks
                    |
                    v
artifacts.py ------- manifests, hashes, seals, environment metadata
                    |
          +---------+----------+
          |                    |
          v                    v
certify.py              bundle.py
installed runtime gate  deterministic portable evidence gate
          |
          v
handoff.py
source, docs, config, tests, manifest, sums, deterministic handoff ZIP
```

## Layer responsibilities

### Contracts

`contracts.py` is the only accepted configuration boundary. It rejects unknown fields, invalid search spaces, overlapping feature roles, mutually exclusive horizon options, and unsupported model names.

### Data boundary

`data.py` normalizes identifiers and timestamps, requires input to already be ordered, checks duplicate keys and finite targets, validates static columns, and requires future exogenous keys to exactly match the forecast horizon.

### Model construction

`factory.py` maps the frozen MLForecast 1.1.0 constructor and fit interfaces. Core and Auto model creation are separate. Auto samplers are explicitly seeded; `seed=1` is the default starting condition.

### Evaluation

`metrics.py` implements Hit@±1-first scoring, bounded MAE tie-breaking, aggregate and position metrics, and deterministic baselines. One fewer Hit@±1 miss must dominate any MAE improvement.

### Execution lifecycle

`runner.py` performs chronological splitting, fitting, prediction, evaluation, prospective sealing, and artifact creation. `runtime.py` verifies actual loadability and repeated prediction rather than treating import or model listing as success.

### Certification

`certify.py` verifies the exact official wheel, installed version, Core Ridge and AutoRidge fit/predict/save/load, trial completion, finite values, key equality, thread settings, process metadata, and generated hashes.

### Portable evidence

`bundle.py` validates a runtime run directory, builds a deterministic ZIP, and independently verifies a received ZIP without extracting it. Runtime status and evidence-integrity status remain separate.

### Source handoff

`handoff.py` packages the MLForecast implementation, tests, configurations, required documents, and snapshots of `pyproject.toml` and `uv.lock`. It requires a clean MLForecast Git scope and generates `ARTIFACT_MANIFEST.json`, `SHA256SUMS`, `SOURCE_PROVENANCE.json`, `VERSION`, a deterministic ZIP, and a sidecar digest.

## Dependency boundary

This PR intentionally does not edit shared dependency files or common workflows. Runtime commands layer the verified local wheel through `uv run --frozen --with <wheel>`. The handoff ZIP includes shared environment files as read-only snapshots, not as proposed modifications.

## Parallelism boundary

Runtime certification uses one process and one thread to reduce nondeterminism. Formal evaluation uses eight outer workers where safe, with model-internal threads constrained to avoid oversubscription and single-GPU contention.
