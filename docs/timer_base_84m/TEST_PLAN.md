# Test Plan

Focused tests cover unknown fields; wrong model, revision, weight, and license; context lower,
upper, and patch boundaries; unsupported horizons, layouts, and covariates; wrong position
counts; non-finite values; duplicate, reverse, future, draw-number gap, and calendar-schedule
chronology; path traversal; remote-code file-set, ordered allowlist, duplicate-key, review-time,
and hash mismatches; missing lock; unapproved review; and pending load and prediction
operations.

CLI tests require completed operations to exit 0, invalid commands to exit 1, pending runtime
states to exit 2, atomic response writing, and preservation of the immutable request file.

PR-B must add real offline snapshot load, CPU/CUDA inference, separate-process replay, exact
shape and finite checks, GPU PID/UUID/VRAM evidence, and post-exit VRAM release.
