# TimesFM 2.5 Provider Protocol

Schema v2 requires a pinned `repo_id` and `revision`, `local_files_only=true`, an explicit backend, GameGeometry, full axis identity, and a ForecastConfig ledger. Unknown keys fail validation.

The schema-v1 compatibility adapter upgrades row-oriented history dynamically and downgrades v2 median output to the legacy first-horizon vector only at the compatibility boundary.
