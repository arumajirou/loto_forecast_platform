# Merlion Data Contract

Two time semantics are explicit:

- `draw_sequence`: requires strictly increasing, unique, gap-free draw numbers and creates
  deterministic synthetic UTC timestamps. The draw-to-timestamp mapping is SHA-256 bound.
- `calendar_time`: preserves supplied timezone-aware timestamps and rejects reordering or
  duplicates.

The provider never silently sorts, fills, deduplicates, interpolates, or repairs input.
Transforms, calibration, thresholds, and hyperparameter selection must be fitted inside
Train only. Holdout and Prospective remain outside this first increment.
