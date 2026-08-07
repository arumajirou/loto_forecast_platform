# Chronos-2 Test Plan

## Fast local gates

1. Python compileall
2. Request validation and fail-closed unknown fields
3. Six game geometries and arbitrary position counts
4. Horizons 1, 2, and 5
5. Local, panel, and multivariate compilation
6. Past/future covariate row contracts
7. Revision and snapshot hashes
8. Quantile shape, finite values, monotonicity, and series identity
9. Schema-v1 compatibility
10. Reference reload response writer

## Final gates

After all implementation is complete: Ruff, mypy, focused pytest, full pytest, coverage, secret scan, dependency audit, then GitHub Actions once. GPU certification is a separate target-host gate and must record PID, UUID, VRAM, device, dtype, attention implementation, and CPU fallback status.
