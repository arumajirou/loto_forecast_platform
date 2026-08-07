# Current State: Chronos-2

Status: `FACT_CHECKED / P0-P4_IMPLEMENTED / GPU_NOT_RUN`

- Base repository SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Legacy branch: `feat/chronos-2-runtime-audit-v1` (read-only evidence source)
- Legacy relation to main: diverged, 9 ahead / 145 behind
- Package: `chronos-forecasting==2.3.1`
- Package source revision: `7dc4435706a4454feb79df44ca9f33631f3027bf`
- Hugging Face revision reviewed on 2026-08-05: `29ec3766d36d6f73f0696f85560a422f50e8498c`
- The legacy and current-reviewed model lanes currently resolve to the same commit. They remain separate lanes so future model-card-only or weight changes cannot silently mix results.

The old provider was limited to Loto7, seven hard-coded positions, one-step inference, context 512, batch 7, seed 42, CUDA, and no cross-learning. Provider v2 removes those shape constants and preserves all requested quantiles.
