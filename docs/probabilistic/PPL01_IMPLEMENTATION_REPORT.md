# Batch PPL-01 実装報告書

## 1. 判定

`REFERENCE_IMPLEMENTATION_COMPLETE / NATIVE_PPL_GRAPHS_PENDING`

本バッチでは、基本設計書・詳細設計書・実装計画書に基づき、確率的プログラミング拡張の共通基盤と、カタログ72モデルすべてに対する実行可能な依存軽量参照経路を実装した。

ただし、PyMC、NumPyro、Pyro、CmdStanPy、BlackJAX、TensorFlow Probability上で、72モデルそれぞれの固有グラフを完全に再現するネイティブ実装は完了していない。ネイティブバックエンドは、パッケージ存在だけでなく実importを検査するprobeと、silent substitutionを禁止するcompatibility contractまでを実装した。

したがって、本成果物は次の状態である。

| 対象 | 状態 |
|---|---|
| 72モデルのカタログ登録 | 完了 |
| 72モデルの参照fit・確率予測 | 完了 |
| posterior draw・HDI要約 | 完了 |
| Hit@±1・MSE罰則decision | 完了 |
| selectゲーム合法decode | 完了 |
| rolling one-step評価 | 完了 |
| protocol hash・execution fingerprint | 完了 |
| 8外側worker・heavy 2・GPU 1制御 | 完了 |
| save/load用posterior reference | 完了 |
| artifact transaction・SHA-256 manifest | 完了 |
| CLI・dry-run・status・diagnose・compare | 完了 |
| PyMC等のbackend import probe | 完了 |
| モデル固有のPyMC/NumPyro/Pyro/Stanグラフ | 未完了 |
| MCMCのR-hat/ESS/divergence実測 | ネイティブ実装後 |
| ArviZ InferenceData/NetCDF正本 | ネイティブ実装後 |

## 2. 実装内容

### 2.1 パッケージ

`src/loto/probabilistic/`に以下を追加した。

- strict contractとstatus taxonomy
- 72モデル・29推論プロファイルのYAMLローダー
- 既存174モデルとの統合ビュー
- model×game×backend×profile compatibility planner
- point-in-time dataset builder
- 参照posterior engine
- posterior predictive drawsと95%区間
- Hit@±1 utility、Hit@±1－MSE utility
- selectゲームの制約付きdynamic programming decode
- rolling evaluationとprotocol別leaderboard
- resource semaphore
- transactional artifact store
- CLIとruntime diagnostics

### 2.2 参照モデルの意味

参照バックエンドは、すべてのモデルIDを実行可能にするための、モデルファミリー別の依存軽量な確率予測実装である。

例:

- 共役系: Dirichlet/Beta型十分統計
- 階層系: global/local partial-pooling analogue
- 回帰・ordinal系: context transition posterior
- 動的系: discounted/segment/regime weighted posterior
- count系: candidate count intensity posterior
- mixture/nonparametric系: bounded mixture of full/recent/transition components
- deep probabilistic系: model別receptive fieldを持つsequence bootstrap posterior
- calibration/ensemble/decision系: OOFを想定した確率変換・utility adapter

これはBART、Gaussian Process、Bayesian Transformerなどのネイティブアルゴリズムと同一であるという主張ではない。各成果物の`posterior_reference.json`には`reference_semantics`を保存し、ネイティブ実装との混同を防止している。

## 3. 検証結果

### 3.1 PPL対象テスト

- 9 tests
- failures: 0
- errors: 0
- skipped: 0

### 3.2 利用可能なリポジトリ回帰テスト

- 628 tests
- failures: 0
- errors: 0
- skipped: 2

次は環境依存不足のため、全体実行から明示的に除外した。

- `neuralforecast`
- `ray`
- `psycopg`
- NeuralForecastを直接要求するAutoHINT 1テスト

### 3.3 72モデル実行

| 実行 | 条件 | 結果 |
|---|---|---|
| smoke | 72モデル、2 rolling points、64 posterior draws | 72/72 PASS |
| standard certification | 72モデル、10 rolling points、64 posterior draws | 72/72 PASS |

標準検証は合成データであり、予測精度の実証ではなく、モデル契約・確率単体性・合法decode・rolling lifecycle・artifact生成の認証である。

## 4. バックエンド状態

この実行環境では、builtin referenceのみ実行可能だった。

PyMCはモジュールが存在したが、PyMCが旧ArviZ APIの`concat`をimportしようとして失敗した。したがって、存在確認だけなら誤ってAVAILABLEになる状態だった。実装ではsubprocess実importを必須に変更した。

他のNumPyro、BlackJAX、Pyro、CmdStanPy、TFPは未導入だった。

## 5. 次バッチ

ネイティブ実装は次の順序が適切である。

1. PyMC/ArviZ互換バージョンの固定と共役4モデル
2. PyMC階層2モデル・回帰・状態空間
3. NumPyro cross-backend reference
4. CmdStanPy代表4モデル監査
5. Pyro deep probabilistic 10モデル
6. mixture/nonparametricの離散潜在推論
7. ArviZ正本、R-hat/ESS/divergence gate
8. sealed holdout・prospective

詳細は既存の`BATCH_PPL01_IMPLEMENTATION_PLAN.md`を参照する。
