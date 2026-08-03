# PPL-01 ネイティブ確率的プログラミング実装報告書

## 1. 結論

PPL-01 の72モデルについて、詳細設計で定義した **主ネイティブ経路を1モデルにつき1経路** 実装した。
`backend_policy: primary_native`を使用すると、各モデルは`native_primary.yaml`で指定された
バックエンドへ固定され、builtin参照実装へ黙って置換されない。

本報告書でいう「72モデルのフル実装」は、次の範囲を指す。

- 72モデルすべてに主実装を割り当てる
- 主実装の確率グラフまたは厳密解析処理を実装する
- 推論、事後確率draw、点予測、診断、保存、比較へ接続する
- 72件のdispatchとplannerを機械検査する
- 主経路と異なるbackendへのsilent substitutionを禁止する

すべてのモデルをPyMC・NumPyro・Pyro・Stan・TFPの全組合せで重複実装する
`all_declared` exhaustive scopeは別スコープであり、本バッチの完了条件には含めない。

## 2. 実装件数

| 主バックエンド | 件数 | 実装内容 |
|---|---:|---|
| builtin | 8 | Dirichlet解析解5件、事後意思決定3件 |
| PyMC | 46 | MCMC、SMC、ADVIによる古典・階層・動的・混合・count・calibrationモデル |
| NumPyro | 6 | HSMM、switching、HDP、sticky HDP-HMM、DP changepoint |
| Pyro | 10 | MLP、TCN、GRU、LSTM、Transformer、VRNN、DMM、Neural HMM等 |
| PyMC-BART | 1 | BART事後予測をカテゴリ確率へ変換 |
| ArviZ | 1 | PSIS-LOO stacking |
| **合計** | **72** | **主経路72/72** |

## 3. 主要な実装ファイル

- `configs/probabilistic/native_primary.yaml`
  - 72モデルの主バックエンド、推論profile、graph IDの正本
- `src/loto/probabilistic/native.py`
  - backend共通の`NativePosterior`
- `src/loto/probabilistic/native_registry.py`
  - 72件の正本読込と件数検査
- `src/loto/probabilistic/models/pymc_native.py`
  - PyMC 46グラフ
- `src/loto/probabilistic/models/numpyro_native.py`
  - NumPyro 6グラフ
- `src/loto/probabilistic/models/pyro_native.py`
  - Pyro 10グラフ
- `src/loto/probabilistic/backends/*_adapter.py`
  - 推論・事後draw抽出・診断
- `src/loto/probabilistic/lifecycle.py`
  - rolling fit/predict、診断、保存、評価
- `tools/verify_native_ppl_implementation.py`
  - 72件の静的・runtime検証

## 4. 推論経路

### PyMC

- NUTS: 連続潜在変数モデル
- SMC: 離散changepoint、HMM、混合・DP系
- Full-rank ADVI: 高次元screening経路
- 事後の`next_probabilities`を`NativePosterior`へ変換
- R-hat、bulk/tail ESS、divergence、BFMI、ELBOを可能な範囲で記録

### NumPyro

- NUTSまたはSVI
- 離散状態をmarginalize／連続緩和した主グラフ
- `Predictive`から`next_probabilities`を抽出

### Pyro

- AutoDiagonalNormal／AutoLowRank guideによるSVI
- profile指定時はNUTSにも対応
- GPU利用は`native_device: auto|cpu|cuda`で制御
- モデル内の重み・潜在状態をsample siteとして定義

### PyMC-BART／ArviZ

- PyMC-BARTはBARTの事後位置予測をカテゴリkernel確率へ変換
- ArviZは4つのDirichlet posterior候補をPSIS-LOO stackingで合成

## 5. silent substitution防止

`backend_policy: primary_native`では、plannerが各model IDについて
`native_primary.yaml`の`primary_backend`と`primary_profile`を直接使用する。
バックエンドが利用不能ならtrialは`BACKEND_UNAVAILABLE`としてBLOCKEDし、builtinへ置換しない。

`tools/verify_native_ppl_implementation.py`は次を検査する。

1. native registryが72件・ID重複ゼロ
2. catalogとregistryのID集合一致
3. backend別件数一致
4. PyMC／NumPyro／Pyro dispatch集合一致
5. native smoke planが72モデルを保持
6. 主backend/profileの置換ゼロ
7. `--require-runtime`時は必要6バックエンドがavailableかつimplemented

## 6. テスト結果

### コード・契約テスト

- probabilistic＋CLI対象テスト: **32 PASS**
- 実行可能なリポジトリ回帰テスト: **634 PASS / 2 SKIP**
- 全収集で未実行: `psycopg`、`neuralforecast`、`ray`不足の既存テスト
- Python compileall: PASS
- Linux shell syntax: PASS
- native registry: 72件
- dispatch source未収載ID: 0
- silent substitution: 0

証跡:

- `audit/ppl01-native-primary/probabilistic-tests.xml`
- `audit/ppl01-native-primary/static-verification.json`
- `audit/ppl01-native-primary/native-coverage.json`

### この作業コンテナでのruntime

利用可能だった主経路はbuiltin 8件とArviZ 1件であり、合成データsmokeは
**9/9 PASS**した。

- `audit/ppl01-native-primary/local_available_run.json`
- `audit/ppl01-native-primary/runs/ppl01-native-local-available/`

このコンテナでは次の制約がある。

- PyMC 5.27.1とArviZ 1.1.0のAPI世代が不整合でPyMC import失敗
- NumPyro、Pyro、PyMC-BARTは未導入

したがって、このコンテナ単独では外部PPL 63経路のruntime PASSを主張しない。
配布先向けに、以前導入実績のある組合せを`requirements-probabilistic-native.txt`へまとめ、
`PPL_INSTALL_MODE=native`と72件runtime smokeを追加した。

## 7. 配布先runtime完了条件

配布先で次をすべて満たしたとき、72主経路のruntime certificationをPASSとする。

1. `verify_native_ppl_implementation.py --require-runtime`がPASS
2. `native_smoke.yaml`のplanが72 allowed／0 blocked
3. 72 trialすべてPASS
4. posteriorがfinite
5. 確率simplexがvalid
6. silent substitution 0
7. 各trialの`posterior_metadata.json`にnative graph IDとlibrary versionが存在

## 8. 既知の範囲外

- Stan、TFP、BlackJAXを含む全宣言backend×modelの網羅実装
- 72モデルの精度優位性の証明
- 大規模full profileの所要時間保証
- 宝くじに予測可能な信号が存在することの保証

これらは実装完了とは分けて評価する。
