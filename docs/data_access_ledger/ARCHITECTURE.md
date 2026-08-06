# Architecture

```text
ledger JSON
   |
   v
Pydantic strict contracts
   |
   +--> canonical JSON / ledger SHA-256
   |
   v
pure validator
   |-- structure and DAG
   |-- dataset identity
   |-- state provenance
   |-- fit/tune availability
   |-- OOF chronology and seeds
   `-- Holdout/Prospective order
   |
   v
ValidationReport (PASS/BLOCKED/INVALID)
```

The package has no database, network, model-runtime, Registry, Prediction Lock, Actual Source, or
workflow dependency. Contracts are immutable evidence descriptions; the validator performs no I/O.
The CLI is the only I/O layer and reads/writes JSON paths supplied by the operator.

The adoption boundary is deliberate: later PRs should emit events from existing orchestration and
formal-backtest pipelines, seal the completed ledger, and run this validator before artifact
registration or promotion. This PR does not modify those pipelines.
