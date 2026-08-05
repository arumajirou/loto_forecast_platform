# Darts first-increment test plan

## Executed local gates

1. Pydantic strict-schema rejection.
2. notorch/CUDA invalid-combination rejection.
3. static export count and uniqueness.
4. optional import failure retention.
5. argument acceptance and fail-closed rejection.
6. draw-number uniqueness, monotonicity and gap-free checks.
7. raw-frame immutability.
8. position-local shape.
9. fake-runtime reproduction of the current two-model regression ensemble.
10. compileall, focused pytest, AST parse and line-length inspection.

## Pending runtime gates

- resolve `darts[notorch]==0.46.1` and `darts[torch]==0.46.1` locks;
- discover real executable model count;
- smoke NaiveDrift, ExponentialSmoothing and RegressionEnsembleModel;
- real save/load/re-predict certification;
- one Torch global-model smoke;
- GPU PID, VRAM and CPU-fallback evidence.
