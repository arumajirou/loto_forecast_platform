# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / CONTRACT_V2_IMPLEMENTED / REAL_RUNTIME_PENDING`

The main branch previously contained a Loto7-only schema-v1 provider that retained only q0.5.
This isolated increment adds a dedicated Moirai 2.0 contract without changing shared workers,
shared catalogs, the root dependency graph, or other foundation-model providers.

Verified in this change: schema validation, dynamic game geometry, draw/calendar time adapters,
token-budget checks, native quantile validation, license fail-closed policy, post-processing, and
legacy schema-v1 conversion. Real `uni2ts` model loading and GPU execution are not claimed.
