# Phase 7 canonical Holdout runner status

Status: `FORMAT_FIX_APPLIED / EXECUTION_PENDING`

Current PR head to verify on native Windows:

- `3c1f14fadbafc2cf1f049e0e7771def130728e2d`

Current pinned identities:

- sealed historical runner SHA-256: `986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187`
- canonical serializer Git blob: `44fe8c8b3149f1a3207370cef2d3e5c5bc6749d7`
- MLForecast: `1.1.0`
- GlobalSklearnTransformer supported state: `FunctionTransformer(func=numpy.log1p, inverse_func=numpy.expm1)` with the exact default flags pinned in `DERIVATION_CONTRACT.json`

Evidence history:

1. Original unstable legacy semantic SHA gate blocked seed 1 before Holdout.
2. Canonical semantic v1 bridge was introduced without changing the sealed historical runner.
3. Native Windows exposed CRLF source-anchor portability; fixed with raw-byte SHA validation first and in-memory newline normalization only.
4. Replay-only v2 reached the real runtime and failed closed before Holdout because `GlobalSklearnTransformer` constructor state was not covered by canonical v1.
5. Serializer/deriver coverage was extended only for the evidence-backed MLForecast 1.1.0 `log1p/expm1` FunctionTransformer state; all other states remain fail-closed.
6. Native Windows verification on head `c953a0e...` produced `17 passed` before Ruff reported format-only diffs in three files.
7. Those three files were formatted only. Formatting changed the serializer Git blob, so deriver and contract pins were refreshed to `44fe8c8b...`.

No current-head Windows PASS is claimed yet.

Next gate:

1. exact-head file/blob verification
2. `py_compile`
3. focused pytest
4. Ruff format + lint
5. real MLForecast `GlobalSklearnTransformer(log1p/expm1)` semantic smoke
6. derive a fresh bundle
7. verify sealed runner unchanged
8. only after that, run a new isolated `--stop-after-replay` 4-seed/80-trial verification

Prohibited until replay-only verification passes:

- Holdout execution
- Holdout actual access
- scoring
- Candidate Freeze mutation
- new HPO
- model reselection
