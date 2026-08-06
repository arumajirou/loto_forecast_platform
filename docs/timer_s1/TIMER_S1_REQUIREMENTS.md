# Timer-S1 requirements

## Functional

- Keep logical model ID `timer-s1` distinct from Timer, Timer Base, Timer-XL, and Time-MoE.
- Support Numbers3, Numbers4, MiniLoto, Loto6, and Loto7 as position-local univariate series.
- Support horizons 1, 2, and 5 in draw-sequence and calendar-time modes.
- Retain exactly q0.1 through q0.9 and use q0.5 as the point forecast.
- Reject samples, native mean claims, covariates, and joint multivariate execution in PR-A.

## Safety

- Reject unknown contract fields.
- Require immutable revisions and SHA-256 evidence before model loading.
- Require an approved exact remote-code allowlist and offline execution.
- Reject future actuals, duplicate timestamps, non-finite data, symlinks, and path escape.
- Return `EXECUTION_PENDING` with `runtime_verified=false` until PR-B runtime certification.
