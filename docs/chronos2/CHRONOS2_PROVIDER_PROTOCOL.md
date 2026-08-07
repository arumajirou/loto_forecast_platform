# Chronos-2 Provider Protocol v2

## Request essentials

`schema_version`, `run_id`, `operation`, `repo_id`, full 40-character `revision`, `game_geometry`, `series_layout`, `position_columns`, `history`, context, horizon, quantiles, cross-learning, batch, device, dtype, attention implementation, seed, and `local_files_only=true`.

## Response essentials

- model identity and effective arguments
- argument ledger with requested/effective values
- point, median, optional mean, and quantile matrices
- prediction index and series identity
- artifact references
- runtime/GPU evidence
- warnings and structured errors

Matrices are `[position][horizon]`. Quantile keys use their decimal level strings, such as `"0.1"` and `"0.9"`.
