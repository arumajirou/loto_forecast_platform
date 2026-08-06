# Execution Schedule

## Scheduling Model

固定納期ではなくGate型。工数は1名相当概算で、CI障害、download、license review、target-host、Holdout/Prospective待ちを含まない。

| Phase | Work | Estimate | Exit Gate |
|---|---|---:|---|
| P0 | Blueprint/freeze | 2–4日 | documents reviewed |
| P1 | Foundation adoption | 5–10日 | #120/#121/#123/#124 policy fixed |
| P2 | Source Registry | 4–7日 | source schema + records |
| P3 | Benchmark fingerprint | 5–8日 | task/budget hashes |
| P4 | Wave 1 providers | 各7–15日 | real runtime + OOF |
| P5 | Wave 2 providers | 各10–20日 | real runtime + OOF |
| P6 | Retrieval | 15–30日 | RAFT/TS-RAG OOF |
| P7 | Adaptive methods | 各10–25日 | method OOF |
| P8 | Cross-provider campaign | 10–30日+計算 | final OOF |
| P9 | Holdout | approval依存 | one-time score |
| P10 | Prospective | calendar依存 | multiple windows |

## Per-Model Gate

A. source intake → B. contract → C. runtime → D. OOF → E. integration。

Aではpaper/code/model/license/revision/hash/dependency。BではGameGeometry、context、horizon、output、remote-code、tests。Cではlock、import、load、CPU/GPU、replay、evidence。Dではfold、seed、baseline、metrics、efficiency。Eではcatalog、worker、CLI/API/UI、full tests。

## Parallelization

並行可能: 異なるsource調査、docs、CPU baseline、static validator、focused tests。

直列化: GPU jobs、shared catalog/worker、DB migration、Holdout、Prospective scoring、promotion。

## Critical Path

```text
CI/PR audit
→ foundation adoption
→ source registry
→ one lightweight provider end-to-end
→ common evaluation
→ additional providers
→ retrieval/adaptive
→ full OOF
→ Holdout
→ Prospective
```

## Stop Conditions

duplicate PR、license不明、hash固定不可、remote-code review失敗、未承認VCS/path dependency、fallback、retrieval leakage、data hash不一致、既存機能破壊。baseline未達は停止ではなく正式結果。
