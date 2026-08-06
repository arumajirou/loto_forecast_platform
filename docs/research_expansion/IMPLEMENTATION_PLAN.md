# Implementation Plan

## Entry Criteria

- PR依存DAG監査済み
- CI #58分類済み
- #120/#121/#123/#124の採否とmerge順決定
- model/methodのID、branch、PR、Issue重複検索
- source/license/revision調査
- Holdout/Prospective未開封
- target host capacity確認
- path ownership決定

## Phases

### Phase 0 — Documentation and Freeze

本資料、candidate source register、blocked/approved intake、path ownership、PR dependency mapを作る。コード変更なし。

### Phase 1 — Foundation Adoption

Version、Strict Configuration、Runtime Certification SDK、Data Access Ledgerをreviewし、exact-byte tests、互換性、merge順、adoption guideを確定する。

### Phase 2 — Research Source Registry

`src/loto/research_sources/**`にsource record、revision/license status、artifact inventory、duplicate ID、supersession、release freshnessを実装する。

### Phase 3 — Benchmark Fingerprint

task/data/split/metric/budget hash、pretraining overlap declaration、contamination status、benchmark adapters、latency/VRAM/parameter Paretoを実装する。

### Phase 4 — Lightweight Model Wave

1. Reverso-Small
2. Granite FlowState
3. Kairos 10M
4. Super-Linear
5. LightGTS

各modelを以下へ分割する。

- PR-A: source、license、strict contract、GameGeometry、focused tests。loadなし。
- PR-B: isolated environment、checkpoint validation、native adapter、#123利用。
- PR-C: reviewed lock、real CPU/GPU、save/reload/replay、evidence review。
- PR-D: chronological OOF、seeds、baselines、metrics。
- PR-E: catalog、worker、CLI/API/UI。最後。

### Phase 5 — Medium/Large Wave

TempoPFN、Kairos 23/50M、Granite PatchTST-FM。Wave 1で共通問題を解消してから開始する。

### Phase 6 — Retrieval

- RET-0: fold-local index contractとleakage proof
- RET-1: RAFT
- RET-2: TS-RAG
- RET-3: common OOF comparison

### Phase 7 — Adaptive Methods

covariate adapter、online adaptation、adaptive ensemble、relational conformal、partition constraint。

### Phase 8 — Full Fair Campaign

同一data/fold/seed/baseline/budget classで全候補を評価し、leaderboard、Pareto、null championを保存する。

### Phase 9 — Holdout

独立approval後にcandidate/protocol/predictionをfreezeし、一度だけscore。結果後のtuningを禁止する。

### Phase 10 — Prospective

actual前にpredictionをlockし、公式Actual取得後に複数windowをscoreする。

## Definition of Done

```text
SOURCE_PINNED
LICENSE_REVIEWED
CONTRACT_TESTS_PASS
ISOLATED_LOCK_REVIEWED
REAL_LOAD_PASS
REAL_INFERENCE_PASS
OUTPUT_SEMANTICS_VERIFIED
CPU_SMOKE_PASS
GPU_FORMAL_PASS_OR_NOT_APPLICABLE
SAVE_RELOAD_PASS
SEPARATE_PROCESS_REPLAY_PASS
OOF_COMPLETE
BASELINES_COMPLETE
MULTI_SEED_COMPLETE
ARTIFACTS_VERIFIED
FULL_REPOSITORY_TESTS_PASS
ACTIONABLE_CI_PASS
```

accuracy gainはDoDではない。未改善なら`RESEARCH_NO_GAIN`で完了する。

## Resource Allocation

共通基盤・統合・検証60–70%、新provider20–30%、探索研究10%。GPU同時実行1、CPU系独立検査は安全範囲で最大8。
