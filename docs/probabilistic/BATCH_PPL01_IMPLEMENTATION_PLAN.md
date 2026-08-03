# Batch PPL-01 実装計画書

**名称**: 確率的プログラミング・ベイズ時系列フルモデル拡張 — 実装計画  
**対象**: `loto_forecast_platform` v3.2.0  
**上位文書**: `BATCH_PPL01_BASIC_DESIGN.md` / `BATCH_PPL01_DETAILED_DESIGN.md`  
**状態**: `PROPOSED / IMPLEMENTATION_PLAN_COMPLETE`  
**作成日**: 2026-08-03  

---

## 1. 目的

72モデル・29推論プロファイルを、既存174モデル、リーク防止、評価、整合性管理を壊さず段階実装する。最終的に`full`で全72モデルを少なくとも1経路試行し、`exhaustive`で互換行列内の全組合せを予算制御付きで実行できる状態を作る。

本計画はカレンダー日数の見積りではなく、依存関係、作業単位、相対規模、検証ゲートを定義する。重い全CIは最後に一括実行するが、構文・unit・変更対象smokeは各バッチで必ず実行する。

## 2. 実装方針

1. **縦切り優先**: 最初にcatalog→dataset→inference→diagnostics→artifact→evaluationの1本を閉形式モデルで通す。
2. **reference first**: 共役モデルのbuiltin閉形式をreferenceとし、PyMC/NumPyro/Stanを照合する。
3. **optional dependency isolation**: backend未導入でも通常CLI/testを壊さない。
4. **typed failure**: unavailable/non-convergence/OOMを成功に見せない。
5. **full bounded**: 全モデルを試すが、無条件直積は行わない。
6. **no silent fallback**: model/backend/profileの変更は別trialとして記録。
7. **8 worker policy**: 外側8ワーカー、GPU1、heavy CPU2を維持。
8. **CI last**: 全CIはrelease gateに集約し、途中はtargeted testsで高速に進める。

## 3. バッチ構成

| Batch | 名称 | 目的 | 依存 | 規模 |
| --- | --- | --- | --- | --- |
| PPL-01.0 | 基線固定・互換性probe | 依存・GPU・コンパイラ・入力正本を確定 | なし | S |
| PPL-01.1 | 契約・カタログ・planner骨格 | 72/29正本、status、hash、compatibilityを実装 | PPL-01.0 | L |
| PPL-01.2 | 共役・階層・経験ベイズ | builtin reference＋PyMC p0経路 | PPL-01.1 | XL |
| PPL-01.3 | NumPyro・BlackJAX | JAX高速経路とcross-backend | PPL-01.2 | L |
| PPL-01.4 | CmdStanPy監査 | 代表4モデルの独立実装監査 | PPL-01.2 | L |
| PPL-01.5 | 回帰・順序・GAM・BART・GP | 外生変数対応確率モデル | PPL-01.2 | XL |
| PPL-01.6 | 動的・状態空間・変化点・HMM | 時間変化モデルとrecovery | PPL-01.2,PPL-01.3 | XL |
| PPL-01.7 | count・mixture・nonparametric | 有界切断付き研究モデル | PPL-01.2,PPL-01.3 | XL |
| PPL-01.8 | Pyro deep probabilistic・TFP隔離 | 深層確率モデル10件 | PPL-01.1 | XL |
| PPL-01.9 | 校正・ensemble・decision | 確率校正と合法decode | PPL-01.2,PPL-01.5 | L |
| PPL-01.10 | full/exhaustive runner・CLI・artifact | 72モデルを予算制御付き実行 | PPL-01.2〜01.9 | XL |
| PPL-01.11 | 評価・sealed holdout・release | 全gate、整合性、文書化 | PPL-01.10 | XL |

### 3.1 モデル割当

| Batch | モデル件数 | 対象ファミリー |
| --- | --- | --- |
| PPL-01.0 | 0 | - |
| PPL-01.1 | 0 | - |
| PPL-01.2 | 11 | conjugate, empirical_bayes, hierarchical |
| PPL-01.3 | 0 | - |
| PPL-01.4 | 0 | - |
| PPL-01.5 | 13 | bayesian_regression, gaussian_process, ordinal, semi_parametric, tree_bayesian |
| PPL-01.6 | 13 | changepoint, dynamic_conjugate, regime_switching, state_space |
| PPL-01.7 | 16 | count, mixture, nonparametric |
| PPL-01.8 | 10 | deep_probabilistic |
| PPL-01.9 | 9 | calibration, decision, ensemble |
| PPL-01.10 | 0 | - |
| PPL-01.11 | 0 | - |

## 4. ブランチ・PR戦略

推奨ブランチ:

```text
feat/ppl01-foundation
feat/ppl01-conjugate-pymc
feat/ppl01-jax-stan
feat/ppl01-regression-dynamic
feat/ppl01-mixture-deep
feat/ppl01-meta-runner
feat/ppl01-release
```

原則:

- 1 PRで複数backendの巨大変更を混ぜない。
- generated catalog/docsだけの差分とruntime実装を分離する。
- PRごとに`scope`, `evidence`, `known blocks`, `rollback`を記載。
- CIを毎PRでフルには回さず、対象testをローカル実行し証跡保存。
- release PRで全CI、integrity、カタログ件数を一括実行。

## 5. 作業分解構造

| Batch | ID | 作業 | 主な配置 | 検証 | 完了条件 |
| --- | --- | --- | --- | --- | --- |
| PPL-01.0 | 0.1 | 入力ZIP・基本設計・catalog SHAを固定 | docs/evidence | hash verification | 全hashをbaseline manifestへ保存 |
| PPL-01.0 | 0.2 | Python 3.13 optional extra解決probe | scripts/probes | probe smoke | 各backendをAVAILABLE/BLOCKEDへ分類 |
| PPL-01.0 | 0.3 | GPU/JAX/PyTorch共存probe | scripts/probes | CUDA allocation probe | 同時実行policyを確定 |
| PPL-01.0 | 0.4 | CmdStan compiler/cache probe | scripts/probes | compile hello model | toolchain statusを記録 |
| PPL-01.0 | 0.5 | 既存pytest基線保存 | audit/ppl01-baseline | targeted tests | PPL追加前の失敗一覧を固定 |
| PPL-01.1 | 1.1 | probabilistic package scaffold | src/loto/probabilistic | import test | optional depsなしでimport成功 |
| PPL-01.1 | 1.2 | Pydantic/dataclass contracts | contracts.py,statuses.py | contract tests | strict extra=forbidとschema version |
| PPL-01.1 | 1.3 | catalog loaderとunified view | catalog.py | catalog tests | 72件、既存衝突0 |
| PPL-01.1 | 1.4 | profile loader | catalog.py/config.py | profile tests | 29件、ID重複0 |
| PPL-01.1 | 1.5 | compatibility reason codes | compatibility.py | matrix tests | 全modelにprimary path |
| PPL-01.1 | 1.6 | hash canonicalization | config.py | hash golden tests | OS/Python差で安定 |
| PPL-01.1 | 1.7 | dataset builder | dataset.py | geometry tests | 6ゲームshape PASS |
| PPL-01.1 | 1.8 | resource class scheduler | resources.py | semaphore tests | 8/light、2/heavy、1/GPU |
| PPL-01.1 | 1.9 | trial planner/dry-run | planner.py | plan snapshot tests | fullで72候補が現れる |
| PPL-01.2 | 2.1 | builtin analytic Dirichlet reference | models/conjugate.py | closed-form recovery | 静的/expanding/rolling PASS |
| PPL-01.2 | 2.2 | discounted/EB Dirichlet | models/conjugate.py | recovery+leakage | holdout不使用 |
| PPL-01.2 | 2.3 | Beta-Binomial/Dirichlet-Multinomial | models/conjugate.py | recovery | 過分散回復 |
| PPL-01.2 | 2.4 | PyMC backend adapter | backends/pymc_adapter.py | backend contract | InferenceData変換PASS |
| PPL-01.2 | 2.5 | hierarchical digits/games | models/hierarchical.py | pooling recovery | 部分プーリング回復 |
| PPL-01.2 | 2.6 | prior predictive gate | predictive.py,diagnostics.py | prior gate tests | 不良priorをinference前拒否 |
| PPL-01.2 | 2.7 | PPL lifecycle/save-load | lifecycle.py,artifact_store.py | reload tests | posterior要約再現 |
| PPL-01.2 | 2.8 | p0 rolling benchmark | runner.py | integration smoke | control/基準比較生成 |
| PPL-01.3 | 3.1 | NumPyro adapter | backends/numpyro_adapter.py | backend contract | CPU NUTS PASS |
| PPL-01.3 | 3.2 | JAX GPU routing | resources.py | GPU evidence | cuda:0、semaphore=1 |
| PPL-01.3 | 3.3 | SVI guides | backends/numpyro_adapter.py | ELBO tests | 3初期値安定性 |
| PPL-01.3 | 3.4 | BlackJAX adapter | backends/blackjax_adapter.py | research smoke | NUTS/Pathfinder/SMC typed result |
| PPL-01.3 | 3.5 | cross-backend conjugate | tests/cross_backend | distribution comparison | 許容差PASS |
| PPL-01.4 | 4.1 | Stan shared data/functions | stan/shared | compile tests | reusable include PASS |
| PPL-01.4 | 4.2 | 代表4モデルStan実装 | stan/models | simulation recovery | PyMC/NumPyroと整合 |
| PPL-01.4 | 4.3 | CmdStanPy adapter | backends/cmdstanpy_adapter.py | backend contract | CSV→InferenceData PASS |
| PPL-01.4 | 4.4 | compile cache/hash | artifact_store.py | integrity test | source/binary hash保存 |
| PPL-01.5 | 5.1 | multinomial logit priors | models/regression.py | coefficient recovery | normal/laplace/horseshoe PASS |
| PPL-01.5 | 5.2 | ordinal models | models/regression.py | ordered recovery | 3方式runtime PASS |
| PPL-01.5 | 5.3 | spline/GAM | models/regression.py | PIT/knot test | train-only basis |
| PPL-01.5 | 5.4 | PyMC-BART | models/regression.py | availability+smoke | UNAVAILABLE/BLOCKEDもtyped |
| PPL-01.5 | 5.5 | GP categorical/time varying | models/regression.py | bounded-size smoke | 入力上限とtimeout |
| PPL-01.5 | 5.6 | feature standardizer artifact | dataset.py,artifact_store.py | reload transform | fold内fit |
| PPL-01.6 | 6.1 | dynamic Dirichlet/logistic-normal | models/dynamic.py | state recovery | innovation scale回復 |
| PPL-01.6 | 6.2 | local level/trend/dynamic regression | models/dynamic.py | trend recovery | forecast transition PASS |
| PPL-01.6 | 6.3 | single/multiple changepoint | models/dynamic.py | location recovery | selection/holdout分離 |
| PPL-01.6 | 6.4 | HMM/HSMM/switching | models/dynamic.py | label-invariant recovery | transition/emission PASS |
| PPL-01.6 | 6.5 | seasonal harmonic | models/dynamic.py | null-signal control | 偽seasonalityを拒否 |
| PPL-01.6 | 6.6 | dynamic rolling evaluation | comparison.py | 500-step smoke | 固定化検査PASS |
| PPL-01.7 | 7.1 | Poisson/NB/Beta-Binomial | models/counts.py | dispersion recovery | offset/exposure PASS |
| PPL-01.7 | 7.2 | zero-inflated/hurdle | models/counts.py | zero mechanism recovery | 単純NB比較 |
| PPL-01.7 | 7.3 | finite mixture/latent class/MoE | models/mixtures.py | label-invariant recovery | bounded components |
| PPL-01.7 | 7.4 | DP/HDP/sticky HDP-HMM | models/mixtures.py | truncation tests | cutoffをmanifest保存 |
| PPL-01.7 | 7.5 | nonparametric budget gates | planner.py | budget tests | 無界trialなし |
| PPL-01.8 | 8.1 | Pyro adapter/param-store isolation | backends/pyro_adapter.py | backend contract | trial汚染0 |
| PPL-01.8 | 8.2 | Bayesian MLP/embedding/ordinal | models/deep.py | SVI recovery | calibration PASS |
| PPL-01.8 | 8.3 | Bayesian TCN/GRU/LSTM/Transformer | models/deep.py | sequence smoke | posterior collapse診断 |
| PPL-01.8 | 8.4 | VRNN/DMM/Neural HMM | models/deep.py | latent recovery | multiple init安定性 |
| PPL-01.8 | 8.5 | checkpoint/reload | artifact_store.py | reload test | guide/optimizer/params保存 |
| PPL-01.8 | 8.6 | TFP quarantine adapter | backends/tfp_adapter.py | isolated smoke | 主環境へ依存漏れなし |
| PPL-01.9 | 9.1 | Bayesian calibration 3方式 | models/meta.py | OOF leakage tests | in-sample calibrationなし |
| PPL-01.9 | 9.2 | BMA/PSIS stacking/DMA | models/meta.py | weight simplex tests | 未来情報なし |
| PPL-01.9 | 9.3 | digits utility rules | decision.py | boundary tests | 0/9境界PASS |
| PPL-01.9 | 9.4 | select constrained decoder | decoder.py | geometry property tests | 合法出力100% |
| PPL-01.9 | 9.5 | probability/point table exporter | predictive.py | schema tests | 既存評価へ接続 |
| PPL-01.10 | 10.1 | runner state machine | runner.py | transition tests | resume/idempotency |
| PPL-01.10 | 10.2 | subprocess worker protocol | inference_engine.py | termination tests | typed exit/status |
| PPL-01.10 | 10.3 | artifact transaction commit | artifact_store.py | crash consistency | 部分成果物をPASS扱いしない |
| PPL-01.10 | 10.4 | CLI commands | cli integration | CLI tests | 全基本設計command実装 |
| PPL-01.10 | 10.5 | observability | observability.py | metric/trace tests | 低cardinality |
| PPL-01.10 | 10.6 | full profile | configs/probabilistic/full.yaml | dry-run/integration | 72全件typed trial |
| PPL-01.10 | 10.7 | exhaustive profile | configs/probabilistic/exhaustive.yaml | budget tests | allowed組合せのみ |
| PPL-01.11 | 11.1 | 既存rolling/sentinel接続 | comparison.py | protocol tests | cross-protocol拒否 |
| PPL-01.11 | 11.2 | multiplicity/promotion | comparison.py | gate tests | champion=None対応 |
| PPL-01.11 | 11.3 | sealed holdout runner | runner.py | visibility tests | 封印解除監査 |
| PPL-01.11 | 11.4 | prospective registry | registry integration | pre-registration tests | 予測時刻証跡 |
| PPL-01.11 | 11.5 | full targeted regression | tests/probabilistic | pytest | 変更範囲PASS |
| PPL-01.11 | 11.6 | 全CI一括 | repository root | pytest/ruff/mypy | 最後に一括PASS |
| PPL-01.11 | 11.7 | integrity/catalog/docs再生成 | INTEGRITY/docs | integrity check | 権威manifest一個 |
| PPL-01.11 | 11.8 | release bundle/handoff | release/ | hash verification | 再現可能bundle |

## 6. バッチ別実装手順

### 6.1 PPL-01.0 基線固定・互換性probe

入力を変更せず、実機でのみ決められる事項を確定する。

成果物:

```text
audit/ppl01-baseline/
├── input_hashes.json
├── existing_test_baseline.json
├── backend_availability.json
├── python_dependency_resolution.log
├── cuda_jax_torch_probe.json
├── cmdstan_probe.json
└── environment.json
```

gate:

- 既存失敗と新規失敗を区別できる。
- backendごとに`AVAILABLE/UNAVAILABLE/BLOCKED`。
- versionはprobe結果からlockし、推測値を記載しない。

### 6.2 PPL-01.1 基盤契約

実装順:

```text
statuses → contracts → catalog/profile loader → compatibility
→ hash/config → dataset → resource scheduler → planner
```

重要gate:

- `uv run python -c 'import loto'`がprobabilistic extraなしで成功。
- unified catalogで既存IDの変更0。
- full dry-runに72件全てが現れ、除外はreason code付き。
- resource schedulerのdeadlock test。

### 6.3 PPL-01.2 共役・階層

最初のend-to-end vertical slice:

```text
pp-static-dirichlet-categorical
→ builtin analytic
→ prior/posterior predictive
→ decision
→ rolling evaluation
→ artifact save/load
```

その後、expanding、rolling、discounted、EB、hierarchicalを追加する。

gate:

- 閉形式のgolden test。
- 同一データでPyMC posterior summaryがreference許容差内。
- Loto系とNumbers系でshape/合法decodeが成立。
- lifecycleの再読込後予測要約が一致。

### 6.4 PPL-01.3/01.4 JAX・Stan監査

NumPyroは速度経路、Stanは独立監査経路として実装する。

cross-backendはposterior drawの完全一致ではなく、次を比較する。

- posterior mean/sd。
- 5/50/95% quantile。
- posterior predictive class probability。
- decision output。

Stan compileはcacheし、source hashとbinary hashを保存する。

### 6.5 PPL-01.5 回帰系

実装順:

1. multinomial normal/laplace。
2. horseshoe/regularized horseshoe。
3. ordinal 3方式。
4. spline/GAM。
5. BART。
6. GP。

各モデルで、feature standardization、reference class、prior、basis/knotをmanifestへ保存する。BART/GPは入力数・行数・runtime budgetを先に制限する。

### 6.6 PPL-01.6 動的系

実装順:

1. dynamic Dirichlet。
2. logistic-normal random walk。
3. local level/trend。
4. dynamic regression/horseshoe。
5. changepoint。
6. HMM/HSMM/switching。
7. seasonal/GP time-varying。

各構造は人工データでrecoverしてから実データへ進む。高Hitだけでなくstateが固定値予測を生んでいないか検査する。

### 6.7 PPL-01.7 count・mixture・nonparametric

元データに意味のあるcount targetを先に定義する。抽選数字自体を根拠なくPoisson化しない。

DP/HDP系はtruncation upper boundを設定ファイルに必須化し、未指定をconfig errorとする。

### 6.8 PPL-01.8 deep PPL

- Pyro param storeをtrial単位で隔離。
- SVI guideとoptimizer stateを保存。
- KL、reconstruction、entropy、prediction diversityを監視。
- deterministic counterpartとの公平比較。
- TFPは隔離workerのみ。

深層モデルはruntime PASSをaccuracy PASSとしない。simulation recovery、複数初期値、sealed rollingを別gateにする。

### 6.9 PPL-01.9 meta layer

calibration:

- fold OOF predictionのみでfit。
- probability before/afterを保存。
- calibrationだけでHit上昇した場合も元model IDとcalibrator IDを連結表示。

ensemble:

- weight simplex、source model fingerprintを保存。
- source modelのprotocol mismatch時は作成拒否。

### 6.10 PPL-01.10 runner

runner completion criteria:

- planがdeterministic。
- job statusはatomic write。
- resumeで成功trialを再実行しない。
- failed trialはpolicyに従い再試行。
- 8 workerのうちheavy/gpu制約を遵守。
- partial runでもreportとmanifestを生成。
- Ctrl+C/SIGTERM後にターミナルが消えてもrun statusが残る。

### 6.11 PPL-01.11 評価・release

順序:

```text
targeted regression
→ full profile dry-run
→ full runtime certification
→ standard rolling evaluation
→ negative controls
→ sealed holdout
→ prospective registration path
→ full pytest/ruff/mypy
→ integrity/catalog/docs regeneration
→ release bundle
```

sealed holdoutは実装確認時に勝手に開封せず、明示コマンドと監査ログを要求する。

## 7. テスト実行方針

### 7.1 各バッチ

例:

```bash
uv run python -m py_compile src/loto/probabilistic/*.py
uv run pytest -q tests/probabilistic/unit tests/probabilistic/contracts
uv run ruff check src/loto/probabilistic tests/probabilistic
```

backend別:

```bash
uv run --extra probabilistic-core pytest -q tests/probabilistic/backends/test_pymc_*.py
uv run --extra probabilistic-jax pytest -q tests/probabilistic/backends/test_numpyro_*.py
uv run --extra probabilistic-torch pytest -q tests/probabilistic/backends/test_pyro_*.py
uv run --extra probabilistic-stan pytest -q tests/probabilistic/backends/test_stan_*.py
```

実際のextra名とversionはPPL-01.0のprobe後に確定する。

### 7.2 release gate

```bash
uv sync --frozen --extra dev --extra probabilistic-full
uv run pytest
uv run ruff check .
uv run mypy src/loto/probabilistic
uv run loto3 catalog --counts
uv run loto3 probabilistic catalog list
uv run loto-integrity check
```

full CIはこの段階で一括実行する。

## 8. simulation recovery計画

各fixtureはseed固定の人工生成器を持ち、生成parameterとposterior recoveryを比較する。

| fixture | models | 判定 |
|---|---|---|
| categorical_simplex | Dirichlet系 | true probabilityがHDI内、平均誤差上限 |
| hierarchical_digits | 階層系 | global/local shrinkage回復 |
| sparse_multinomial | horseshoe | nonzero feature識別、false discovery guard |
| dynamic_logits | state-space | latent path/innovation回復 |
| changepoint | CP | 位置許容範囲 |
| hmm | HMM系 | relabel後transition/emission |
| overdispersed_counts | NB/BB | mean/dispersion |
| zero_process | ZI/hurdle | zero mechanism |
| mixture | mixture/DP | predictive distribution、label invariant |
| deep_latent | VRNN/DMM | posterior collapseなし、calibration |

閾値はfixtureごとに定義し、全familyへ同じ数値を適用しない。

## 9. リソース運用

### 9.1 8並列

```text
outer worker = 8
light slots = 8
medium slots = 4
heavy slots = 2
exclusive slots = 1
gpu slots = 1
```

heavy MCMCが2件走っている間、残りworkerはclosed-form、artifact、diagnostic、queue待機を行う。単一GPUへ複数PPL jobを同時投入しない。

### 9.2 failure budget

`exhaustive`には次を必須化する。

- `max_trials`
- `budget_hours`またはbackend別budget unit
- `max_failures`
- `max_consecutive_failures`
- `max_artifact_bytes`

上限到達時は`BUDGET_EXHAUSTED`で正常停止し、未実行trialを一覧化する。

## 10. 成果物とレビュー証跡

各PRで最低限保存:

```text
audit/ppl01/<batch-id>/
├── commands.log
├── test-results.json
├── changed-files.txt
├── catalog-counts.json
├── known-failures.json
├── environment.json
└── SHA256SUMS
```

巨大posteriorはGitへ入れず、run artifactとして管理する。小型golden fixtureだけをtestsへ含める。

## 11. 変更管理

### 11.1 schema migration

- PPL schemaは`1.0.0`から開始。
- field追加はminor、意味変更/削除はmajor。
- loaderはschema不明時に推測変換せず拒否。
- migration scriptは入力を上書きせず新ファイルを作る。

### 11.2 catalog generation

- YAMLが正本。
- Markdown一覧、件数、compatibility reportは生成物。
- 手動編集した生成物をCIで検出。

## 12. ロールバック

- optional extrasを外せば既存174モデル経路が動くこと。
- probabilistic CLI登録をfeature flagで無効化可能。
- unified catalogを無効化してexisting catalogのみへ戻せる。
- PPL artifactは既存runsと別root。
- DB schema変更を初期バッチでは行わない。registry統合は後段で追加テーブルまたはJSON artifact参照とする。

## 13. リスク別中止条件

| リスク | 中止/保留条件 | 処置 |
|---|---|---|
| dependency conflict | core環境の既存testを壊す | backend別環境へ隔離 |
| repeated divergence | reparameterization後も診断FAIL | modelをBLOCKED |
| GPU OOM | 最小許可profileでも失敗 | CPU経路またはBLOCKED、silent変更なし |
| false skill | negative controlでも改善 | sentinel trip、championなし |
| prediction collapse | mode share/entropy gate失敗 | ranking除外 |
| compute explosion | budget超過 | BUDGET_EXHAUSTEDで停止 |
| artifact explosion | storage上限超過 | posterior thinningではなく保存policyを明示変更し別run |

## 14. 受入条件

### 14.1 機能

- 72モデル全件が`IMPLEMENTED/UNAVAILABLE/BLOCKED`のいずれか。
- fullで全72件にtyped trial result。
- exhaustiveでallowed組合せを予算制御実行。
- fit/prior/infer/diagnose/PPC/decision/save/loadの各契約。
- 6ゲームのgeometry対応。

### 14.2 品質

- leakage tests PASS。
- simulation recovery対象family PASS。
- cross-backend代表4モデル PASS。
- non-converged結果はleaderboard除外。
- protocol mismatch比較拒否。
- hash verification PASS。

### 14.3 運用

- 8 worker、GPU1、heavy2。
- resume/idempotency。
- terminal interruptionからstatus回復。
- observabilityとresource evidence。
- final integrity manifestの一元性。

### 14.4 予測精度

全モデル実装完了と、精度改善の証明は別条件とする。実装完了後も正式条件を満たすモデルがなければ`champion=None`を正常結果として受け入れる。

## 15. 次モデルへの引継ぎ要点

1. 基本設計・詳細設計・実装計画の順に読む。
2. YAML正本から件数を再計算し、72/29を手書きしない。
3. PPL-01.0 probeなしにversion pinを推測しない。
4. 最初の実装は`pp-static-dirichlet-categorical`の縦切り。
5. 既存lifecycleのLoto7固定shapeを直接一般化して全回帰を起こさず、PPL lifecycleを分離する。
6. `protocol_hash`と`execution_fingerprint`を混同しない。
7. CIは最後に一括だが、targeted testは各バッチで実行する。
8. silent substitutionを禁止する。
