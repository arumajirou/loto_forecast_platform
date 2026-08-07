# Moirai 2.0 Handoff

PR #83 is the P0-P6 base, PR #86 is the P7 covariate layer, and P8 continues only on
`feat/moirai2-runtime-certification-v1`. Do not retarget or write to either parent branch.

On the target host, generate and review the isolated lockfile, perform frozen synchronization, and
create an explicit request containing a pinned local snapshot path. Run the P8 certification CLI
into a new output directory. Never reuse or overwrite a previous Run ID.

Certification must retain two different provider PIDs, exact point and q0.1-q0.9 prediction hashes,
model config/weight hashes, covariate hashes, forward tensor devices, stdout/stderr, exit codes, and
external GPU samples. CUDA formal success also requires one GPU UUID, provider PID visibility,
positive VRAM, no CPU fallback, and provider PID absence after exit.

Do not open Holdout or Prospective data. Keep all stacked PRs Draft until real supported-lane and
CUDA13 execution, Ruff, mypy, focused tests, one final full pytest, and one actionable CI run pass.
