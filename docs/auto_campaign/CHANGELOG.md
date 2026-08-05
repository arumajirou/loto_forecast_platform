# Changelog

## v1.0.0 - 2026-08-04

- Added runtime BaseAuto subclass registry.
- Added explicit BaseAuto, NeuralForecast, and fit argument coverage catalog.
- Added search-domain catalog and deterministic pairwise plan.
- Added persistent Ray and Optuna AutoModel trial implementations.
- Added MiniLoto U-Shared, U-Local, M-Joint, and H-HINT data tracks.
- Added smoke, HPO, OOF, holdout, prospective, monitor, and verification commands.
- Added best-model save/load/predict and CUDA certification.

## v1.1.0 - 2026-08-04

- Fixed Validation replay configuration IDs to use collision-free deterministic
  enumeration instead of extracting decimal digits from Ray trial IDs.
- Corrected NeuralForecast `PredictionIntervals` construction for v3.2.0.
- Added an executed Optuna callback API coverage case.
- Added the complete required documentation and artifact handoff set.
- Added installer and package-integrity acceptance checks.
- Expanded every successful Trial bundle with CPU `state_dict.pt`, requested and
  effective configuration comparison, parameter statistics, runtime, GPU PID,
  prediction-before/after Parquet files, metrics, and complete SHA-256.
- Added worst-fold Hit@±1 aggregation and strict required-file verification.
- Added code/data/Git/version provenance to run and task manifests.
