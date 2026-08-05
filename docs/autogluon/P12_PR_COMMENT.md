## P12 official AutoGluon 1.5.0 API compatibility audit

Status: `PARTIALLY_VERIFIED / STATIC_OFFICIAL_SOURCE_AUDIT / REAL_RUNTIME_PENDING`

The schema-v2 execution path was compared against the official AutoGluon 1.5.0
`TimeSeriesPredictor` public API and rendered source.

Implemented:

- added an explicit AutoGluon 1.5.0 constructor / fit / predict keyword contract;
- validate generated execution-plan keyword names before importing or running AutoGluon;
- require HPO dictionaries to contain `num_trials`, `scheduler`, and `searcher`;
- require positive integer trials, `scheduler="local"`, and a documented searcher;
- limit HPO string presets to the documented `auto` and `random` values;
- reject unknown HPO keys and unsupported public API keywords with
  `AUTOGLUON_API_CONTRACT_MISMATCH`;
- preserve the existing execution-plan error classifications by delegating those errors to
  the base provider.

Local verification against the exact files committed for P12:

- AutoGluon-focused tests: **63 passed**;
- compileall: **PASS**;
- changed Python lines over 100 characters: **0**;
- remote files match the recorded P12 SHA-256 snapshot;
- branch remains behind `main` by 0;
- no new pull-request workflow run was observed for the `[skip ci]` commits.

This is not runtime certification. Real AutoGluon 1.5.0 fit, predict, HPO, save/load,
CPU fallback, GPU PID/VRAM evidence, Ruff, mypy, full pytest, and a complete GitHub
Actions result remain pending. PR #57 must remain Draft and must not be merged or marked
ready for review.
