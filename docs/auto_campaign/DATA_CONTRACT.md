# DATA_CONTRACT

## Input

Default source:

```text
runs/data-acquisition-all/mini/normalized/mini.csv
```

Required semantic fields:

- one draw ID column selected from configured candidates;
- one monotonically increasing integer draw index, generated only when absent;
- five finite numeric position columns P1 through P5.

## Validation

The loader rejects:

- missing number columns;
- non-numeric or non-finite values;
- duplicate draw IDs;
- duplicate draw indices;
- order violations;
- insufficient rows for the configured Train/Validation/Holdout/OOF split.

The loaded frame is never written back to the raw source.

## Temporal boundaries

- Holdout: final 20 draws.
- Validation: 50 draws immediately before Holdout.
- Train: every earlier draw.
- OOF: five expanding endpoints strictly before Validation.
- Prospective: next not-yet-observed horizon after the complete known dataset.

## Track representation

- U-Shared: five `unique_id` series in one panel.
- U-Local: one position series per model task.
- M-Joint: five-series multivariate panel with `n_series=5`.
- H-HINT: TOTAL plus P1-P5 and a 6x5 summing matrix.
