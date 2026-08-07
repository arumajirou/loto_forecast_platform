# Moirai 2.0 Handoff

PR #83 remains the P0-P6 contract base. Continue P7 only on
`feat/moirai2-covariate-runtime-v1`; do not modify or retarget PR #83.

The next target-host gate is to resolve the isolated lockfile and run three separate cases:

1. target-only;
2. past-only covariates;
3. past-only plus known-future covariates.

For each case, retain request, response, ordered feature names, input shapes, matrix hashes, future-tail hash, token geometry, all nine quantiles, PID/device evidence, and a unique Run ID. Run both
draw-sequence and calendar-time cases. Do not open Holdout or Prospective data. Keep both PRs Draft
until real Uni2TS execution, Ruff, mypy, focused tests, full pytest, and one actionable CI run pass.
