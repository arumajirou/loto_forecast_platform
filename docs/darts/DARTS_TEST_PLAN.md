# Darts contract test plan

## Executed local gates

1. Pydantic strict-schema rejection.
2. notorch/CUDA invalid-combination rejection.
3. static export count and uniqueness.
4. optional import failure retention.
5. argument acceptance and fail-closed rejection.
6. draw-number uniqueness, monotonicity and gap-free checks.
7. raw-frame immutability.
8. position-local, multivariate, and global-sequence shape contracts.
9. fake-runtime reproduction of the current two-model regression ensemble.
10. chronological Train/Holdout isolation.
11. Hit@±1, position-wise Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE.
12. deterministic Random, fixed, mean, median, last, frequency, and seasonal baselines.
13. fake-model save/load/re-predict equality and failure evidence retention.
14. Prospective SHA-256 sealing and tamper detection.
15. expanding-window OOF fold adjacency and non-overlap.
16. identical fold coverage across multiple seeds.
17. per-seed mean, population variance, and worst-value retention.
18. rejection of best-seed-only adoption.
19. baseline mean/worst Hit@±1 champion gate and `NO_CHAMPION` result.
20. data/config/code provenance hash stability and tamper sensitivity.
21. nine-model Local statistical identity and failure-retention matrix.
22. six-model Regression identity matrix and estimator-factory contract.
23. target/past lag leakage rejection and future-lag coverage checks.
24. position-local and global-sequence Regression execution contracts.
25. MLForecast parity payload stability and tamper sensitivity.
26. Regression constructor/fit/predict no-silent-drop enforcement.
27. ten-model Torch identity, shared training, and per-model isolation contracts.
28. GPU parameter/prediction device, PID, VRAM, and CUDA-memory evidence.
29. CPU fallback and requested/effective accelerator mismatch rejection.
30. four-model Foundation identity and capability-matrix SHA-256.
31. immutable Foundation model revision and local-artifact manifest requirements.
32. zero-shot optimizer-step/parameter-change rejection.
33. fine-tuning effectiveness and TiRex partial-fine-tuning restrictions.
34. Foundation covariate capability drift and unsupported-input rejection.
35. Foundation package/model dependency failure retention.

## Pending runtime gates

- resolve `darts[notorch]==0.46.1` and `darts[torch]==0.46.1` locks;
- discover the real executable model count;
- run the real P5 Local statistical and P6 Regression matrices;
- run real P7 Torch models with device, PID, and memory evidence;
- pin unresolved Chronos2 and TiRex Hugging Face revisions;
- generate and verify portable local Foundation model manifests;
- run P8 zero-shot and fine-tuning tracks with real models;
- verify real Foundation covariate and probabilistic behavior;
- run real multi-seed OOF using identical cross-library conditions;
- certify real save/load/checkpoint behavior;
- run repository Ruff and full pytest after a hosted runner starts normally.
