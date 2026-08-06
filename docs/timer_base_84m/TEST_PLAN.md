# Test Plan

Focused tests cover unknown fields; wrong model, revision, weight, and license; context lower,
upper, and patch boundaries; unsupported horizons, layouts, and covariates; wrong position
counts; non-finite values; duplicate, reverse, future, and gap chronology; path traversal;
remote-code file-set and hash mismatches; missing lock; unapproved review; and pending load
and prediction operations.

PR-B must add real offline snapshot load, CPU/CUDA inference, separate-process replay, exact
shape and finite checks, GPU PID/UUID/VRAM evidence, and post-exit VRAM release.
