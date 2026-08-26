# Loto Forecast Runtime Audit Handoff

Updated: 2026-08-26T14:44:44.978789+09:00

## Current overall status

- estimated progress: `48%`
- Phase 4A Darts GPU smoke: `VERIFIED`
- Phase 4B GluonTS latest P6 lifecycle: `VERIFIED`
- Phase 4C GluonTS compat P6 lifecycle: `VERIFIED`
- Phase 4D Darts no-torch CPU lifecycle: `VERIFIED`
- Phase 4E sktime classic Python 3.12 CPU lifecycle: `VERIFIED`
- Phase 4F sktime core Python 3.13 CPU lifecycle: `VERIFIED`
- Phase 4G StatsForecast Python 3.13 CPU lifecycle: `VERIFIED`
- Phase 4H Toto 2.0 4M Python 3.12 CUDA lifecycle: `VERIFIED`
- source SHA: `0a13c287e0f0fcc8f983be3512654524dad18b2c`

## Phase 4H

- selected runtime: `/mnt/e/env/ts/loto_forecast_platform/.runtime-envs/toto/bin/python`
- Python: `3.12.13`
- Torch: `2.13.0+cu130` / CUDA `13.0`
- Toto packages: `toto-2=2.0.0`, `toto-models=1.0.0`
- model: `Datadog/Toto-2.0-4m` @ `8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9`
- requested/execution contract: `CUDA full inference`
- provider GPU PIDs: `[3808075, 3808613]`
- peak VRAM bytes: `373293056`
- CPU fallback: `False`
- two-process exact replay: `True`
- dependency/lock mutation: `False`
- accuracy ranking: `False` (Phase 6 remains pending)

## Next

Phase 4 ready queue is complete. Continue with Phase 5 argument-effectiveness validation before Phase 6 all-model/all-game accuracy evaluation.
