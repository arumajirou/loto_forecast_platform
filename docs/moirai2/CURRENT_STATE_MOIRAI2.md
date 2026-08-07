# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P8A_IMPLEMENTED / TARGET_HOST_EXECUTION_PENDING`.

PR #83 provides P0-P6 Contract v2, PR #86 provides P7 native covariate wiring, and PR #87
provides the P8 two-process runtime certifier. P8A adds the target-host execution layer without
opening OOF, Holdout, Prospective, shared workers, shared catalogs, or production promotion.

P8A first requires a reviewed isolated `uv.lock`, a successful `uv run --frozen` import/device
probe, and an explicit pinned local snapshot. It then creates six deterministic runtime requests:

draw-sequence and calendar-time, each with target-only, past-only, and past-plus-known-future
covariates. Cases execute strictly serially to avoid GPU PID and VRAM evidence contamination. Each
case invokes the P8 certifier, which still performs two independent provider-process loads.

Formal runtime certification is true only when all six cases pass. A subset may be useful for
diagnosis, but it cannot set `formal_runtime_certified=true`. No real Uni2TS load, real CUDA run,
full repository test, accuracy metric, or successful GitHub Actions step is claimed by this change.
