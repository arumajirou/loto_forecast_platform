# NeuralForecast 全AutoModel網羅キャンペーン 再設計仕様

## 1. 目的

NeuralForecastのインストール済みバージョンに存在するすべてのAutoModelを対象に、次の3階層の引数を明示的に設定・実行・保存・検証する。

1. `BaseAuto(...)`の共通引数
2. `NeuralForecast(...)`の共通引数
3. `NeuralForecast.fit(...)`の共通引数
4. 各AutoModelの`default_config`およびモデル固有引数

全実験は時間順のTrain、Validation、Holdout、Prospective分割を守り、最優先指標をHit@±1とする。

---

## 2. 現行実装の判定

現在のAutoTFTキャンペーンは以下のみを対象としている。

* AutoTFT
* 7対象
* 最良設定
* Rolling Holdout
* 最終モデル
* 保存、ロード、再予測検証

したがって、以下は未実施である。

* AutoTFT以外のAutoModel
* すべてのモデル固有探索空間
* BaseAuto共通引数の分岐
* Ray／Optuna両backend
* 多変量AutoModel
* AutoHINT
* 全Trialモデル保存
* 全AutoModel間の公平な比較

現在実行中のAutoTFT正式Runは、今後次の区分へ変更する。

```text
stage=pilot_autotft_persistence_certification
formal_all_auto_campaign=false
```

最終的な「全Autoモデル実行完了」の件数には加算しない。

---

## 3. 正式なモデルレジストリ

公式Modelsページは34 AutoModel variantsと説明しているが、ローカルのNeuralForecast 3.2.0では、単純な`名前がAutoで始まるクラス`検索に37件が出ている。37件には通常モデルの`Autoformer`が誤って含まれるため、文字列接頭辞では判定しない。

正式な抽出条件は次とする。

```python
name in neuralforecast.auto.__all__
and inspect.isclass(cls)
and issubclass(cls, BaseAuto)
```

NeuralForecast 3.2.0の現在の想定対象は次の36クラスである。

### 3.1 標準・単変量系AutoModel：24

```text
AutoAutoformer
AutoBiTCN
AutoDLinear
AutoDeepAR
AutoDeepNPTS
AutoDilatedRNN
AutoFEDformer
AutoGRU
AutoInformer
AutoKAN
AutoLSTM
AutoMLP
AutoNBEATS
AutoNBEATSx
AutoNHITS
AutoNLinear
AutoPatchTST
AutoRNN
AutoTCN
AutoTFT
AutoTiDE
AutoTimesNet
AutoVanillaTransformer
AutoxLSTM
```

### 3.2 `n_series`必須の多変量AutoModel：11

```text
AutoMLPMultivariate
AutoRMoK
AutoSOFTS
AutoSOFTSSharp
AutoStemGNN
AutoTSMixer
AutoTSMixerx
AutoTimeMixer
AutoTimeXer
AutoXLinear
AutoiTransformer
```

### 3.3 特殊階層モデル：1

```text
AutoHINT
```

AutoHINTは通常のAutoModelと異なり、`cls_model`、`S`、階層構造を必要とするため、専用Trackで実行する。公式ドキュメントでも、AutoHINTは階層予測とreconciliation用の特殊モデルとして扱われている。

モデル件数を36でハードコードはしない。実行時にレジストリを再生成し、以下を保存する。

```text
AUTO_MODEL_REGISTRY.json
AUTO_MODEL_REGISTRY.csv
AUTO_MODEL_REGISTRY.parquet
AUTO_MODEL_REGISTRY.sha256
```

バージョン更新で件数が変わった場合は、差分を検出してRunを停止する。

---

## 4. 「引数を網羅的に実行」の定義

連続値の`loguniform`や`uniform`、広い整数範囲には無限または非常に多数の候補があるため、全値の直積実行は不可能である。

正式な「網羅」は次の4条件で定義する。

### 4.1 API引数網羅

全引数について、必ず次のいずれかの状態を記録する。

```text
EXECUTED
EXECUTED_ALTERNATE
FIXED_BY_DATA_CONTRACT
NOT_APPLICABLE
UNSUPPORTED_BY_VERSION
FAILED
```

引数の無言省略は禁止する。

### 4.2 有限カテゴリ網羅

`tune.choice([...])`等の有限候補は、すべての値を最低1回実行する。

### 4.3 数値範囲網羅

整数、uniform、loguniform等は最低限次を実行する。

```text
下限付近
25%点
中央値
75%点
上限付近
追加ランダムサンプル
```

loguniformは線形中点ではなく対数空間上の分位点を使う。

### 4.4 組合せ網羅

全直積ではなく、次の順序で実施する。

```text
単一因子網羅
pairwise組合せ網羅
境界値組合せ
BasicVariantGeneratorによる追加探索
```

すべての引数ペアが最低1回共存するpairwise coverageを保証する。

---

## 5. BaseAuto引数の実行設計

対象引数は17個である。

```python
BaseAuto(
    cls_model,
    h,
    loss,
    valid_loss,
    config,
    search_alg=BasicVariantGenerator(random_state=1),
    num_samples=10,
    time_budget=None,
    refit_with_val=False,
    verbose=False,
    alias=None,
    backend="ray",
    callbacks=None,
    ray_options=None,
    optuna_options=None,
    cpus=None,
    gpus=None,
)
```

BaseAutoはValidation lossを使って時系列順の検証を行い、最良設定を選択する。公式仕様上、AutoModelの探索には有効なValidation期間が必要である。

| 引数               | 正式実行                                    | 追加coverage            |
| ---------------- | --------------------------------------- | --------------------- |
| `cls_model`      | 全35基礎モデル                                | AutoHINT互換モデルを別検証     |
| `h`              | `1`                                     | `5`は別ablation         |
| `loss`           | モデル既定、互換MAE                             | MSE、分布loss等           |
| `valid_loss`     | モデル互換loss                               | MAE、MSE、外部Hit@±1再順位付け |
| `config`         | 公式default_config＋固定制御値                  | 全キーcoverage           |
| `search_alg`     | `BasicVariantGenerator(random_state=1)` | 別seed、Optuna sampler  |
| `num_samples`    | `10`                                    | Smoke=`1`、拡張=`30`以上   |
| `time_budget`    | `None`                                  | 制限時間あり                |
| `refit_with_val` | `False`                                 | `True`契約テスト           |
| `verbose`        | `False`                                 | `True`契約テスト           |
| `alias`          | 一意の明示名                                  | `None`契約テスト           |
| `backend`        | `ray`                                   | `optuna`全モデルSmoke     |
| `callbacks`      | 永続化callback必須                           | `None`契約テスト           |
| `ray_options`    | 明示設定                                    | `None`契約テスト           |
| `optuna_options` | Optuna Trackで明示                         | Ray TrackではN/A        |
| `cpus`           | Trialごとに明示                              | 1 CPU契約テスト            |
| `gpus`           | Trialごとに明示                              | CPU実行は契約テストのみ         |

各AutoX wrapperは、内部で対応する`cls_model`をBaseAutoへ渡す。公式実装では各AutoModelが対応モデルと固有の`default_config`を定義している。

---

## 6. NeuralForecast引数の実行設計

```python
NeuralForecast(
    models,
    freq,
    local_scaler_type=None,
    local_static_scaler_type=None,
)
```

| 引数                         | 正式実行                  | coverage                                               |
| -------------------------- | --------------------- | ------------------------------------------------------ |
| `models`                   | 原則1 AutoModelずつ       | 複数モデル同時登録Smoke                                         |
| `freq`                     | `1`                   | 不正値拒否テスト                                               |
| `local_scaler_type`        | `None`を公平比較の主条件       | `standard`, `robust`, `robust-iqr`, `minmax`, `boxcox` |
| `local_static_scaler_type` | 実staticデータがなければ`None` | 合成契約データで全scaler                                        |

NeuralForecast 3.2.0では、同一インスタンス内のモデルは同一`h`でなければならない。そのため`h=1`と`h=5`を同じ`NeuralForecast`へ混在させない。利用可能なlocal scalerも実装から列挙して固定する。

---

## 7. fit引数の実行設計

```python
fit(
    df=None,
    static_df=None,
    val_size=0,
    val_df=None,
    use_init_models=False,
    verbose=False,
    id_col="unique_id",
    time_col="ds",
    target_col="y",
    distributed_config=None,
    prediction_intervals=None,
)
```

### 重要な修正

`val_size=0`は`NeuralForecast.fit`のAPI既定値だが、AutoModelの正式なハイパーパラメータ探索ではValidationが必要である。

正式HPOでは次のどちらか一方を使う。

```text
A. val_size=50, val_df=None
B. val_size=0, val_df=<明示Validation>
```

`val_size`と`val_df`の同時使用は禁止されている。

| 引数                     | 正式実行              | coverage              |
| ---------------------- | ----------------- | --------------------- |
| `df`                   | Trainデータ          | 保存datasetを使う`df=None` |
| `static_df`            | 実データがなければ`None`   | 合成契約データ               |
| `val_size`             | `50`              | `0`＋`val_df`          |
| `val_df`               | `None`            | 明示Validation branch   |
| `use_init_models`      | `False`           | `True`再初期化テスト         |
| `verbose`              | `False`           | `True`                |
| `id_col`               | `unique_id`       | 別名列契約テスト              |
| `time_col`             | `ds`              | 別名列契約テスト              |
| `target_col`           | `y`               | 別名列契約テスト              |
| `distributed_config`   | ローカル正式Runでは`None` | Spark契約Track          |
| `prediction_intervals` | 主比較では`None`       | Conformal Track       |

`distributed_config`を実行していない状態で「fit全引数実行済み」と表示してはならない。Spark契約Track未実施なら、全体状態を`PARTIAL_API_COVERAGE`とする。

---

## 8. モデル固有configの網羅

各AutoModelについて次を実行時に取得する。

```python
auto_cls.get_default_config(
    h=h,
    backend=backend,
    n_series=n_series,
)
```

保存対象：

```text
モデル名
対応cls_model
constructor signature
default_config原本
変換後config
全configキー
探索domainの型
有限候補
数値範囲
依存条件
h依存値
n_series依存値
外生変数対応
```

成果物：

```text
AUTO_DEFAULT_CONFIG_CATALOG.parquet
AUTO_CONFIG_DOMAINS.parquet
AUTO_CONFIG_COVERAGE_PLAN.parquet
AUTO_CONFIG_COVERAGE_RESULT.parquet
```

各キーには次を保存する。

```text
planned_count
executed_count
covered_values
uncovered_values
coverage_rate
failure_count
```

`num_samples=10`だけでは多数のカテゴリ値や連続範囲を網羅できない。したがって、10 TrialのHPOとは別にcoverage Trialを実行する。公式default_configには`tune.choice`、`randint`、`uniform`、`loguniform`等が使われている。

---

## 9. 公平なデータTrack

現在の`block_h1`、`block_h5`はAutoTFT固有の実験設計なので、全AutoModelの主比較から外す。

### Track U-Shared

単変量AutoModel 24種を、5系列のglobal/shared modelとして実行する。

```text
unique_id=P1...P5
h=1
n_series不要
```

### Track U-Local

単変量AutoModel 24種を、位置別の独立モデルとして実行する。

```text
P1専用
P2専用
P3専用
P4専用
P5専用
```

### Track M-Joint

`n_series`必須の11モデルを5系列同時入力で実行する。

```text
n_series=5
h=1
```

### Track H-HINT

AutoHINT用に次の正当な加法階層を作る。

```text
TOTAL=P1+P2+P3+P4+P5
BOTTOM=[P1,P2,P3,P4,P5]
```

評価はBOTTOMのP1～P5に対して行い、TOTAL整合性も別途検査する。

### Legacy Track

既存の次の結果は参考ablationとして残す。

```text
block_h1
block_h5
AutoTFT pairwise search
```

主ランキングには混ぜない。

---

## 10. 時系列分割

全モデルで同じ境界を使用する。

```text
Train       最初からValidation直前まで
Validation  Holdout直前の50抽せん
Holdout     最後の20抽せん
Prospective 実測未判明の次回以降
```

処理順：

```text
1. Train内でconfig生成
2. Train内でScaler・Encoder fit
3. ValidationでHPO
4. 最良候補をTrain内OOFで再評価
5. Train＋Validationで再学習
6. Holdout 20抽せんをRolling評価
7. Prospective予測を実測前にSHA-256固定
```

Holdoutをconfig選択、feature選択、モデル選択に使用しない。

---

## 11. Hit@±1を中心にしたモデル選択

BaseAuto内部ではモデル互換の`valid_loss`を使用する。

ただし、BaseAutoが返す最小Validation lossモデルを、そのまま正式最良モデルとはしない。

全Trialを保存し、外部選択層で次の辞書順に再順位付けする。

```text
1. Validation Hit@±1 最大
2. 全位置Hit@±1 最大
3. MAE 最小
4. RMSE 最小
5. seed最悪Hit@±1 最大
6. 推論失敗率 最小
```

保存指標：

```text
Hit@±1
位置別Hit@±1
全位置Hit@±1
Exact Hit
MAE
MSE
RMSE
valid draw rate
推論時間
Peak VRAM
```

分布予測モデルでは、mean、median、必要なquantileを保存し、同じpoint prediction規則で比較する。

---

## 12. Trialとモデルの全件保存

最良モデルだけでなく、成功したすべてのTrialを保存する。

```text
models/
├── <auto_model>/
│   ├── <track>/
│   │   ├── search/
│   │   │   └── trial_<id>/
│   │   ├── oof/
│   │   │   └── seed_<seed>/fold_<fold>/
│   │   ├── holdout/
│   │   │   └── seed_<seed>/origin_<origin>/
│   │   └── final/
```

各bundle：

```text
requested_config.json
effective_config.json
config_diff.json
base_auto_args.json
neuralforecast_args.json
fit_args.json
state_dict.pt
neuralforecast/
trial_metrics.parquet
prediction_before_save.parquet
prediction_after_load.parquet
parameter_statistics.parquet
runtime.json
gpu_pid.json
load_predict_verification.json
manifest.json
SHA256SUMS
```

Ray Trialが終了した時点でcallbackによりcheckpointを正本ディレクトリへコピーする。Ray一時ディレクトリだけに保存してはならない。

---

## 13. 複数seedとOOF

最良seedだけを採用しない。

最低限：

```text
search_seed = [1]
model_seed  = [1, 42, 2026]
OOF folds   = 5 expanding windows
```

各モデルについて保存する。

```text
mean
standard deviation
minimum
maximum
worst seed
worst fold
```

正式ランキングでは平均値と最悪値を併記する。

---

## 14. ベースライン

すべて同じHoldoutで比較する。

```text
Random
固定値
平均
中央値
直近値
頻度
Naive
HistoricAverage
SeasonalNaive
AutoARIMA
AutoETS
AutoTheta
```

統計モデルはNeuralForecastのAutoModel件数には含めず、比較対象として別管理する。

---

## 15. 実行プロファイル

### P0 Inventory

```text
全AutoModel抽出
signature抽出
default_config抽出
引数catalog生成
実行件数確定
```

### P1 Contract Smoke

```text
36/36 import
36/36 instantiate
36/36 fit
36/36 predict
36/36 save
36/36 load
36/36 predict after load
```

最小データ、`num_samples=1`で行う。

### P2 Argument Coverage

```text
全有限値
数値分位点
pairwise
Ray／Optuna分岐
Scaler分岐
fit引数分岐
```

### P3 Formal HPO

```text
BasicVariantGenerator(random_state=1)
num_samples=10
backend=ray
Validation=50
```

### P4 OOF Certification

```text
5 folds
3 seeds
mean/std/worst
```

### P5 Holdout

```text
20 Rolling origins
予測固定
モデル全件保存
```

### P6 Prospective

```text
実測判明前に予測保存
UTC時刻
SHA-256
コードHash
データHash
Git commit
```

---

## 16. 並列実行設計

ユーザー要件どおり8ワーカー構成を維持する。

```text
logical_workers=8
gpu_concurrency=動的
```

RTX 5070 Ti 16GBでは次の順に制御する。

```text
軽量モデル  最大4 GPU同時
中量モデル  最大2 GPU同時
重量モデル  最大1 GPU同時
残りは待機キュー
```

Trialの正式設定をVRAM都合で無断変更しない。

OOM時：

```text
1. 同じ設定でGPU concurrencyを下げて再試行
2. 同じ設定で単独GPU再試行
3. 再失敗ならFAILED_OOM
```

CPUへ無断fallbackしない。

---

## 17. 成功条件

全AutoModel要件を満たしたと表示できるのは、以下がすべてPASSした場合だけである。

```text
Runtime AutoModel registry        全件検出
Non-Auto false positive           0
Import                            全件PASS
Instantiation                     全件PASS
Default config catalog            全件PASS
Common argument catalog           32引数すべて分類
Finite category coverage          100%
Numeric-domain coverage           計画値100%
Pairwise coverage                 100%
Contract fit/predict              全件PASS
Successful Trial persistence      100%
Load/predict verification         100%
Prediction finite                 100%
CPU fallback                      0
OOF                               全正式モデル
Multiple seeds                    3以上
Holdout                           20 origins
Prospective freeze                SHA-256 PASS
Baselines                         全件完了
Global SHA256SUMS                 PASS
```

一部モデルがライブラリ不具合や依存関係で実行できない場合、全体状態は次とする。

```text
PARTIAL
```

モデル名、設定、例外、再試行、環境、依存関係を保存し、成功扱いにしない。

---

## 18. 実装構造

```text
src/loto/auto_campaign/
├── registry.py
├── signatures.py
├── config_domains.py
├── coverage_planner.py
├── data_tracks.py
├── scheduler.py
├── persistence.py
├── verification.py
├── metrics.py
├── selection.py
└── manifests.py

configs/auto_campaign/
├── campaign.yaml
├── argument_coverage.yaml
├── model_overrides.yaml
├── loss_compatibility.yaml
└── resource_profiles.yaml

tests/auto_campaign/
├── test_registry.py
├── test_signature_catalog.py
├── test_config_coverage.py
├── test_time_split.py
├── test_no_leakage.py
├── test_persistence.py
├── test_load_predict.py
├── test_gpu_evidence.py
└── test_manifest.py

scripts/experiments/
├── inventory_all_neuralforecast_auto.py
├── smoke_all_neuralforecast_auto.py
├── run_all_neuralforecast_auto_coverage.py
├── run_all_neuralforecast_auto_hpo.py
├── run_all_neuralforecast_auto_oof.py
├── run_all_neuralforecast_auto_holdout.py
└── monitor_all_neuralforecast_auto.py
```

---

## 19. 現在のAutoTFT Runの扱い

現在のAutoTFT正式Holdoutは停止・削除しない。

用途を次へ限定する。

```text
永続化機構の認証
GPU 4並列の認証
ロード・再予測の認証
SHA-256成果物生成の認証
```

全AutoModelキャンペーンでは、次を再利用しない。

```text
AutoTFTの既存最良config
既存Validation選択結果
既存ランキング
```

全モデルと同じ新しい分割・探索計画・Run IDでAutoTFTも最初から再実行する。

---

## 20. 最終判定

旧設計：

```text
AutoTFTのみ
最良設定中心
全Auto要件未達
```

新設計：

```text
35標準AutoModel
1特殊AutoHINT
全36クラス
BaseAuto 17引数
NeuralForecast 4引数
fit 11引数
モデル固有config全キー
有限値全件
数値範囲分位点
pairwise coverage
Ray＋Optuna
Trial全件保存
OOF＋複数seed
Holdout＋Prospective
```

この新設計が、当初の「公式ModelsページにあるAutoモデルを、引数を網羅的に設定して実行する」という要件の正式な実装範囲である。
