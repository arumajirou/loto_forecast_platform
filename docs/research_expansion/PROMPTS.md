# GitHub Implementation Prompts

## Master Orchestrator

```text
@GitHub

対象:
https://github.com/arumajirou/loto_forecast_platform

docs/research_expansion/ を基準に、最新研究候補を重複なく証拠駆動で段階実装する。

開始前に再取得:
- default branch / latest main HEAD
- open PR / branch / issue
- PR #120, #121, #123, #124
- model_id、repo_id、class名、別表記
- catalog、worker、provider、docs、tests
- paper、official code/model、license、revision

禁止:
- main直接変更、force push、merge、auto-merge、Ready化
- Holdout開封、Prospective actual access
- source/license/revision推測
- common Runtime SDK、status、manifest、ZIP、GPU monitorの再実装
- 複数providerを一PRへ混在
- best seedだけの採用

手順:
1. duplicate audit
2. source/license gate
3. one model/method only
4. latest mainから独立branch
5. Draft PR
6. focused tests
7. real runtimeは別Gate
8. OOFはruntime後
9. catalog integrationは最後

Hit@±1、MAE/MSE/RMSE、position/all-position Hit@±1、複数seedの平均/分散/worst、全baselineを保持する。未実行はNOT_EXECUTED、未確認はUNVERIFIEDと記録する。
```

## Source Intake

```text
@GitHub

TARGET_MODEL=<model>
MODEL_ID=<logical-id>
EXPECTED_PAPER=<paper>
EXPECTED_CODE=<official-code>
EXPECTED_MODEL_REPO=<repo>

今回はsource/provenance/licenseとstrict intake contractだけ。download、install、load、inference、catalog登録を行わない。

確認:
- latest main
- duplicate ID/branch/PR/issue
- docs/research_expansion/SOURCE_REGISTER.md
- catalog
- PR #121/#123/#124

成果物:
paper/code/model relationship、source/model revision、file inventory、size/hash、code/weight license、remote-code policy、isolated lane、GameGeometry、output semantics、focused tests、必須docs、manifest、SHA256SUMS。

Draft only。runtime/accuracyを主張しない。
```

## Runtime Adapter

```text
@GitHub

TARGET_MODEL=<model>
SOURCE_PR=<approved PR>

前提:
source contract review、#123利用、license/revision固定、isolated lane承認。

実装:
native input、offline snapshot、package/model identity、load、point/quantile/sample extraction、shape/finite/chronology、provider-specific save/load hook、common SDK adapter。

再実装禁止:
subprocess、GPU monitor、status、manifest、SHA256SUMS、ZIP、replay verifier。

real model未実行ならfixture PASSのみ。catalog/worker/APIは変更しない。
```

## Target-host Certification

```text
@GitHub

exact branch/commitを確認しtarget hostでreal runtimeを実行・検証する。

必須:
clean worktree、Git HEAD、reviewed uv.lock、offline snapshot、checkpoint hash、CPU smoke、CUDA formal、provider/GPU PID、UUID、VRAM、devices、no fallback、save/reload、distinct processes、replay、post-exit release、complete manifest。

CUDA available表示だけでPASSにしない。fixture/mock/syntheticはformal禁止。Holdout/Prospectiveに触れない。
```

## Retrieval Contract

```text
@GitHub

TARGET_METHOD=Fold-local Retrieval Index
BRANCH=feat/retrieval-index-contract-v1

RAFT/TS-RAG本体より先に、leakage防止contract、index manifest、validator、focused testsだけを実装する。

必須:
- each OOF fold index = its Train only
- candidate future fully observed in Train
- Validation/Holdout/Prospective exclusion
- self/future exclusion
- top-k IDs/distances
- index SHA
- Data Access Ledger boundary
- no model runtime

global index、validation member、cutoff crossing、self leakage、stale index、tamperを拒否する。Draft/add-only/no catalog。
```

## Fair OOF

```text
@GitHub

TARGET_PROVIDER=<provider>
RUNTIME_EVIDENCE=<real bundle>

前提:
source/license/runtime verified、no Holdout/Prospective、data/protocol/budget fixed。

実行:
chronological expanding OOF、same folds、all approved seeds、target/covariate variants、raw/reconciled predictions、Hit@±1、position/all-position、MAE/MSE/RMSE、probabilistic metrics、mean/variance/worst seed、worst fold、全baseline、latency/VRAM/parameter Pareto、no automatic champion/promotion。

baseline未達はRESEARCH_NO_GAINとして保存する。
```

## Partition-Constrained Sampler

```text
@GitHub

TARGET_METHOD=Exact one-per-position constrained sampler
GAMES=Numbers3,Numbers4

普通のk-DPPでposition制約を保証しない。数学契約、小規模全列挙agreement、exact sampler、seed、marginals、save/load、focused testsを実装する。

disjoint partitions、one per partition、total cardinality、qualified IDs、brute-force agreement、Conditional Bernoulli/autoregressive controls。catalog登録とaccuracy claimは禁止。
```

## Final Integration

```text
@GitHub

source/runtime/OOFの全親証拠を再取得し、catalog/worker/CLI/API/UIへの最小統合だけを実装する。

条件:
source pinned、license reviewed、actionable CI、full tests、real runtime、OOF、baseline comparison、no unresolved review。

capability metadata、正しいstatus、dynamic GameGeometry、dispatch、read-only evidence links、rollback、互換性。

自動promotion、Holdout、Prospective、専用certifier、unsupported claim禁止。
```
