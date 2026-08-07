# PR Roadmap

## Rules

- 最新mainから独立PRを原則とする。
- stacked PRは親merge後にretargetと再検証。
- #123の代わりとなるmodel専用certifierを作らない。
- #121の代わりとなるconfig schemaを作らない。
- #124の代わりとなるleakage ledgerを作らない。
- catalog登録は最後。
- 一PR一model/method。
- source/contractとreal runtimeを分離。

## Foundation

| ID | Title | Depends | Output |
|---|---|---|---|
| DOC-01 | Research Expansion Blueprint | main | 本資料 |
| SRC-01 | Research Source Registry | DOC-01 | source/license/revision |
| BENCH-01 | Benchmark Fingerprint | SRC-01,#121 | task/budget/contamination |
| BASE-01 | Lightweight Baseline Inventory | BENCH-01 | baseline adapters |
| ADOPT-RTC-01 | Runtime SDK Adoption | #123 | migration rules |
| ADOPT-DAL-01 | Data Ledger Adoption | #124 | pipeline integration |

## Model Series

命名:

```text
feat/<model-id>-source-contract-v1
feat/<model-id>-runtime-adapter-v1
feat/<model-id>-target-host-certification-v1
feat/<model-id>-oof-evaluation-v1
feat/<model-id>-shared-integration-v1
```

適用対象:

- Granite FlowState: FLOW-A → B → C → D → E
- Reverso-Small: REV-A → B → C → D → E
- Kairos 10M: KAIROS10-A → B → C → D → E
- TempoPFN: TEMPO-A → B → C → D → E
- PatchTST-FM: PTFM-A → B → C → D → E
- LightGTS、Super-Linearも独立series

Kairos 23/50Mは10M review後に開始する。

## Method Series

### Retrieval

`RET-C0 contract/index` → `RET-RAFT1` → `RET-TSRAG1` → `RET-EVAL1`

### Covariate

`COV-C0 contract` → `COV-A1 availability/mutation` → `COV-M1 adapter/LoRA` → `COV-E1`

### Online

`ONLINE-C0 state machine` → `ONLINE-A1 delayed actual` → `ONLINE-M1 adapter` → `ONLINE-E1 prequential`

### Constrained Output

`PART-C0 constraint` → `PART-M1 exact sampler` → `PART-DPP1 research` → `PART-E1 Numbers3/4`

## Merge Gate

integration PRはsource pin、license review、actionable CI、full tests、real runtime、no fallback、OOF、baseline set、independent review完了後だけ。

## Freeze / Supersede

- stale parent branch
- common SDK重複
- synthetic testだけの次phase
- source/license不明runtime
- 同一model ID並行provider
- catalog登録だけのPR
