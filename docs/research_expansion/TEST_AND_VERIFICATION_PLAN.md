# Test and Verification Plan

## Test Layers

### T0 Source

URL/repository identity、revision、file inventory、SHA-256、license、remote-code、dependency、secret absence。

### T1 Contract

unknown key、strict type、bool/int、NaN/Inf、GameGeometry、horizon、context、unsafe path、hash、UTC、covariate、output inventory。

### T2 Adapter

native input、series/time identity、mask、covariate、quantile/sample extraction、point semantics、raw/reconciled、seed。

### T3 Runtime

real import、load、input、inference、shape、finite、parameter/input/output device、provider PID、GPU PID/UUID/VRAM、fallback rejection、save/reload、process A/B replay、PID release。

### T4 Leakage

Train外fit、future feature、target fold retrieval、future neighbor、actual before lock、online update before actual、fold overlap。

### T5 Evaluation

Hit@±1、position/all-position、MAE/MSE/RMSE、seed aggregation、worst fold、baseline completeness、identical postprocess、missing/duplicate cells。

### T6 Artifact

manifest、SHA256SUMS、tamper、extra/missing、symlink、traversal、deterministic archive、relocation、partial failure。

### T7 Integration

catalog ID、dispatch、worker、CLI、API、UI、registry payload、互換性。

## Model-Specific Acceptance

- FlowState: q0.1–q0.9、sampling rate、context/horizon、r1.0/r1.1分離
- TempoPFN: 38M identity、long context、synthetic flag、loader review
- Kairos: remote-code byte review、dynamic patches、10M先行、variant分離
- Reverso-Small: 550Kのみ、CPU latency、dependency、unavailable release拒否
- PatchTST-FM: 99 quantiles、large weight、memory matrix、ID collision拒否
- LightGTS: period tokenizer、negative control、isolated Transformers、remote code
- Super-Linear: expert inventory、spectral weights、resampling、CPU budget

## Validation Order

開発中:

1. targeted pytest
2. compileall
3. AST/JSON/YAML parse
4. line length
5. secret scan
6. manifest
7. smoke

完了後:

8. Ruff
9. mypy
10. focused regression
11. real provider runtime
12. target-host evidence review
13. related subsystem tests
14. full pytest
15. actionable GitHub CI

## Claim Boundary

| Evidence | Allowed claim |
|---|---|
| schema fixture | contract logic |
| fake executor | orchestration logic |
| synthetic GPU record | evidence schema |
| real CPU process | CPU runtime |
| real GPU PID/VRAM | GPU runtime |
| OOF | historical generalization estimate |
| Holdout | one-time held-out result |
| Prospective | pre-actual locked result |

上位claimへ自動変換しない。

## Statistical Review

seed事前固定、多重比較補正、confidence/bootstrap interval、baseline delta、effect size、worst seed/fold、family leave-one-out、best-seed禁止、post-Holdout tuning禁止。
