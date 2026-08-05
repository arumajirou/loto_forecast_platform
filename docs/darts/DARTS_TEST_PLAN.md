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
36. complete chronological historical-forecast origin generation.
37. exact boolean and integer-cadence retrain schedules.
38. prefit evidence requirement for `retrain=false`.
39. complete origin/target/position historical-record coverage.
40. manual Hit@±1 and Darts backtest MAE/MSE/RMSE parity.
41. `actual - prediction` residual sign, order, shape, and numeric parity.
42. optimized versus general historical forecast prediction parity.
43. historical API no-silent-drop ledger and policy/record SHA-256.
44. four-model ensemble/conformal identity retention and identity SHA-256.
45. chronological Train, calibration, and evaluation partition enforcement.
46. unavailable base-model and per-task failure retention.
47. pre-fitted global-model and output-chunk-shift compatibility rules.
48. constructor, fit, and predict scoped no-silent-drop argument ledger.
49. `NaiveEnsembleModel` arithmetic-mean parity.
50. regression stacking key completeness and evaluation-leakage rejection.
51. conformal quantile ordering, uniqueness, median, and pair validation.
52. `ConformalQRModel` probabilistic-base requirement.
53. conformal quantile non-crossing and base-median parity.
54. nominal/empirical interval coverage, width, and all-position metrics.
55. P10 matrix failure isolation, SHA-256 tamper sensitivity, and immutability.
56. exact Local/Regression/Torch/Foundation/Ensemble/Conformal coverage.
57. manual save, terminated-process load, and disk-reload evidence.
58. model ID, class path, parameter hash, shape, finite, and allclose replay.
59. artifact size and SHA-256 stability between save and load.
60. global clean-save training and covariate state removal.
61. Torch manual companion `.ckpt` requirement.
62. best and last checkpoint selection and training-state restore.
63. initialized-model weights and encoder restoration.
64. `map_location=cpu` and CPU device certification.
65. `map_location=cuda` and full GPU PID/VRAM certification.
66. CPU fallback rejection after CUDA request.
67. save/load/checkpoint/weights argument no-silent-drop ledger.
68. P11 matrix failure retention and evidence SHA-256.
69. exact eight-track cross-library provider retention.
70. Darts wrapper, standalone provider, and base-algorithm identity validation.
71. pinned execution/base revisions and model-config SHA-256 requirements.
72. common data, split, fold, seed, lag, covariate, and Train-only fit scopes.
73. target/past-lag leakage and target-as-covariate rejection.
74. exactly one canonical execution for every duplicated base algorithm.
75. GPU effective-device, PID, and VRAM evidence with CPU-fallback rejection.
76. complete seed/fold/target/position prediction-key parity across providers.
77. Hit@±1, position Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE.
78. per-seed mean, population variance, and worst-value retention.
79. wrapper prediction/metric deltas without algorithm double counting.
80. optional strict wrapper prediction parity and drift rejection.
81. canonical-only champion selection with all seven baseline families.
82. P12 provider failure retention, report SHA-256, and tamper sensitivity.
83. exact 12-document final handoff membership and canonical order.
84. missing and unexpected final-package document rejection.
85. nested, absolute, backslash, and traversal path rejection.
86. SHA256SUMS generation, ordering, parsing, and duplicate-entry rejection.
87. source tamper and stale-checksum rejection before packaging.
88. byte-identical deterministic ZIP output from identical source documents.
89. fixed ZIP timestamps and normalized `0644` file modes.
90. ZIP CRC, extraction, and byte-for-byte source comparison.
91. output ZIP isolation from the source document directory.
92. ZIP-level and content-manifest SHA-256 reporting.

## Pending runtime gates

- resolve `darts[notorch]==0.46.1` and `darts[torch]==0.46.1` locks;
- discover the real executable model count;
- run the real P5 Local statistical and P6 Regression matrices;
- run real P7 Torch models with device, PID, and memory evidence;
- pin unresolved Chronos2 and TiRex Hugging Face revisions;
- generate and verify portable local Foundation model manifests;
- run P8 zero-shot and fine-tuning tracks with real models;
- verify real Foundation covariate and probabilistic behavior;
- run real P9 `historical_forecasts`, `backtest`, and `residuals` calls;
- certify real optimized/general parity and exact retraining counts;
- run real P10 ensemble and conformal models on identical OOF folds and seeds;
- certify real stacking separation, interval coverage, and interval width;
- run real P11 manual, clean, checkpoint, weights, and cross-device paths;
- certify real process restart, artifact SHA-256, and prediction replay;
- certify real GPU PID, VRAM, CUDA allocation, and CPU fallback behavior;
- run all eight P12 provider tracks on identical data, folds, seeds, and features;
- certify real Darts wrapper versus standalone prediction and metric deltas;
- certify deduplicated algorithm ranking and the complete baseline champion gate;
- run real multi-seed OOF using identical cross-library conditions;
- certify real save/load/checkpoint behavior;
- regenerate the deterministic handoff package with final run IDs and verified hashes;
- run repository Ruff and full pytest after a hosted runner starts normally.
