# StatsForecast Python 3.13 runtime lane

This isolated project is consumed by `scripts/run_statsforecast_runtime_lane.py`.
The runner copies this manifest into a run-owned environment directory, resolves a fresh
`uv.lock`, syncs with `--locked`, and stores the lock as certification evidence.

The root project dependency graph is not modified. A checked-in lock is intentionally not
fabricated in a network-blocked environment.
