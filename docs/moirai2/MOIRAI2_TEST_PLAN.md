# Moirai 2.0 Test Plan

Focused order:

1. package/model/source constants and license policy;
2. unknown-key rejection and schema-v1 conversion;
3. GameGeometry and position counts 1/3/4/5/6/7;
4. draw-sequence and calendar-time mapping;
5. horizons 1/2/5 and token geometry;
6. all-quantile shape, finite state, monotonicity, and q0.5 point extraction;
7. covariate length/chronology rejection;
8. CPU fallback rejection;
9. deterministic constrained integer projection;
10. compileall, Ruff, mypy, focused pytest, then one final full pytest.

Real snapshot load, separate-process reload, GPU PID, VRAM, and no-fallback certification remain
target-host execution gates.
