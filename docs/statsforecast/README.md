# StatsForecast isolated contract

This directory is the first conflict-free implementation increment for the StatsForecast
campaign. It does not change the shared worker, catalog, root dependency files, workflow,
CLI, or top-level README.

Implemented contracts:

- 41-entry project inventory: the upstream public model surface plus the existing `CES`
  project extension;
- explicit expected outcomes instead of requiring every model to behave identically;
- `NaNModel` expected-negative finite-value validation;
- immutable draw-sequence and calendar-time data contracts;
- integer `ds` with `freq=1` only for draw-sequence mode;
- chronological Train/Validation/Holdout separation;
- Hit@±1-first evaluation and required baselines;
- injected-runtime discovery and forecast validation;
- Prospective SHA-256 sealing before actual values are known.

Real StatsForecast 2.1.1 runtime certification remains pending. Static contracts and fake
runtime tests do not prove package installation, model construction, fit, forecast,
cross-validation, intervals, exogenous-variable effects, distributed execution, or
save/load behavior.
