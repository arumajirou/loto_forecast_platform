# TimesFM 2.5 Specification

The v2 request/response models are defined under `src/loto/adapters/timesfm25/`. Pydantic uses `extra="forbid"`. Formal ranking horizons are 1, 2, and 5; the wire contract permits up to 1024 for later boundary testing.

A successful response has matrices shaped `[series_count, prediction_length]` for median and mean, plus nine matrices keyed `0.1` through `0.9`. `series_identity` and `prediction_index` preserve axis identity.
