# Basic Design

## Goal

最新研究を縦割りstackではなく、共通基盤上の薄いproviderとして導入する。

```text
Research Source Registry
  → Strict Config (#121)
  → Data / Retrieval Governance (#124)
  → Provider Adapter
  → Runtime Certification SDK (#123)
  → Chronological OOF
  → Holdout Gate
  → Prospective Lock / Actual Scoring
  → Registry / Promotion / Monitoring
```

## Principles

1. **Evidence before registration**: catalog登録は最後。
2. **Common SDK first**: process、GPU監視、replay、manifest、ZIPをproviderで再実装しない。
3. **Gate delivery**: SOURCE → CONTRACT → DEPENDENCY → LOAD → CPU → GPU → OOF → HOLDOUT → PROSPECTIVE → REGISTRY → PRODUCTION。
4. **Runtime and accuracy separation**: 動作成功は予測改善を意味しない。
5. **Null champion**: 条件を満たさなければ`champion=null`。
6. **Raw immutability**: 原本を上書きしない。
7. **No best-seed cherry-pick**: 全seedを保持する。

## Architecture Families

- SSM/Efficient: FlowState、TempoPFN、Reverso-Small
- Adaptive Tokenization: Kairos
- Large Patch FM: Granite PatchTST-FM
- Periodic/Frequency: LightGTS、Super-Linear
- Retrieval: RAFT、TS-RAG
- Constrained Output: partition-matroid sampler

## Intake Priority

### Wave 1

1. Reverso-Small
2. Granite FlowState
3. Kairos 10M
4. Super-Linear
5. LightGTS

### Wave 2

1. TempoPFN
2. Kairos 23M
3. Kairos 50M
4. Granite PatchTST-FM

### Wave 3 — Research only

TimeFound、Xihe、YingLong、VisionTS、TimePro、KRNO。公式weight、license、revision確認前にruntime PRを作らない。

## Common Evaluation Matrix

| Axis | Values |
|---|---|
| game | Numbers3, Numbers4, MiniLoto, Loto6, Loto7 |
| horizon | 1, 2, 5 |
| formulation | position-local, panel-batched, shared/joint when valid |
| exogenous | target-only, past-only, known-future |
| mode | zero-shot, adapter/LoRA when supported |
| split | Train, Validation, Holdout, Prospective |
| output | raw point, quantile/sample, reconciled point |
| baseline | Random, fixed, mean, median, last, frequency, statistical |

## Decision Policy

- source/license不明 → `BLOCKED_SOURCE`
- dependency未解決 → `BLOCKED_DEPENDENCY`
- real load失敗 → `BLOCKED_RUNTIME`
- OOFでbaseline未達 → `RESEARCH_NO_GAIN`
- seed/fold不安定 → `RESEARCH_UNSTABLE`
- Holdout未承認 → `HOLDOUT_LOCKED`
- Prospective未評価 → `PROSPECTIVE_PENDING`
- 全Gate通過 → production review

自動promotionは行わない。
