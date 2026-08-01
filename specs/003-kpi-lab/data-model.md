# Data Model: KPI Lab

## Core entities

- `LabConfig`: immutable game, KPI, budget, controls, and stopping configuration.
- `KpiDefinition`: game, tolerance, fixed ticket count, and definition hash.
- `CostModel`: ticket cost and explicitly unavailable expected-return fields.
- `CoverResult`: selected tickets, coverage, method, bounds, gap, and trace.
- `Proposal`: schema-validated bounded search suggestion.
- `KpiMeasurement`: n, interval, e-value, efficiency, source, and KPI hash.
- `EProcessState`: log wealth, observation count, alpha, and decision state.
- `LedgerEntry`: previous hash, payload hash, sequence, timestamp, and entry hash.
- `Termination`: terminal state, reason, evidence, and budget consumption.

## Integrity rules

1. KPI definition hash is fixed before search.
2. Ticket count is positive and fixed.
3. Efficiency cannot exceed the packing-bound-derived maximum.
4. Sealed data cannot be opened from a search state.
5. Ledger sequence and hash chain are continuous.
6. Solver method is explicit in every `CoverResult`.
