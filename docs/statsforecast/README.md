# StatsForecast isolated contract

This directory is the first conflict-free implementation increment for the StatsForecast
campaign. It does not change the shared worker, catalog, root dependency files, workflow,
CLI, or top-level README.

Implemented contracts:

- exact 41-entry StatsForecast 2.1.1 `statsforecast.models.__all__` inventory, including
  `ConformalSeasonalPool`;
- explicit expected outcomes instead of requiring every model to behave identically;
- `NaNModel` expected-negative finite-value validation;
- immutable draw-sequence and calendar-time data contracts;
- integer `ds` with `freq=1` only for draw-sequence mode;
- chronological Train/Validation/Holdout separation;
- Hit@±1-first evaluation and required baselines;
- complete runtime-inventory gating and identity-preserving forecast validation;
- Prospective SHA-256 sealing before actual values are known;
- package-enabled runtime certification CLI and durable per-model evidence.

Real StatsForecast 2.1.1 runtime certification remains pending. Static contracts and fake
runtime tests do not prove package installation, model construction, fit, forecast,
cross-validation, intervals, exogenous-variable effects, distributed execution, or
save/load behavior.
