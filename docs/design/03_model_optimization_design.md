# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. モデル採用原則

全公開モデルを無差別に同時実行しない。モデルレジストリへ登録し、互換性検査、ライセンス、依存、資源見積、smoke、外側CVの順で段階昇格する。Hugging Face候補はAPI検索で継続収集するが、正式比較セットは予算内で凍結する。

## 2. P0正式比較モデル

| ファミリー | モデル | タスク | 理由 |
|---|---|---|---|
| 理論 | Uniform、Frequency、Dirichlet shrinkage | candidate | 必須基準 |
| 理論 | Order-statistic ±1 decoder | position | 学習なしの±1上限基準 |
| StatsForecast | HistoricAverage、Naive、WindowAverage | position/indicator | 低コスト基準 |
| StatsForecast | AutoARIMA、AutoETS、AutoTheta、AutoCES | position | 自動統計 |
| StatsForecast | ADIDA、CrostonSBA、TSB | candidate indicator | 疎系列 |
| MLForecast | AutoRidge、AutoElasticNet | position | 小標本正則化 |
| MLForecast | AutoLightGBM、AutoXGBoost、AutoCatBoost | position | 非線形ラグ |
| sklearn | Logistic、HistGB、ExtraTrees | candidate | 37数字二値分類 |
| NeuralForecast | DLinear、NLinear | position | 強い線形DL基準 |
| NeuralForecast | NHITS、TiDE、TCN、GRU | position/candidate | 優先ニューラル |
| ESN | Echo State Network | position | 小標本・高速 |

## 3. P1高精度候補

| ライブラリ | モデル |
|---|---|
| NeuralForecast | NBEATS/NBEATSx、DeepAR、BiTCN、TFT、PatchTST、TimesNet、TSMixer/x、TimeMixer、iTransformer、TimeXer、KAN、RMoK、SOFTS、StemGNN、VanillaTransformer、Informer、AutoFormer、FedFormer、TimeLLM |
| AutoGluon | TimeSeriesPredictor標準モデル、DirectTabular、RecursiveTabular、WeightedEnsemble、Chronos-2 |
| Darts | RegressionModel、LightGBMModel、RandomForest、NBEATS、NHiTS、TCN、TFT、Transformer、TiDE、NeuralForecastModel |
| GluonTS | DeepAR、Transformer、DeepState、MQCNN/DeepNPTS等の確率モデル |
| PyTorch Forecasting | TFT、NHiTS、NBEATS、DeepAR、RecurrentNetwork |
| Tabular | TabPFN/TabPFN-TS、CatBoost ranking、LambdaMART |

## 4. P2時系列基盤モデル

| モデル群 | モード | 優先用途 |
|---|---|---|
| Chronos-Bolt Tiny/Small | zero-shot/fine-tune | 位置・indicator、低VRAM |
| Chronos-2 Small/Base | zero-shot/LoRA/full | 共変量、ensemble |
| IBM Granite TinyTimeMixer | zero-shot/fine-tune | 多trial、軽量 |
| TimesFM 2.5 | zero-shot/fine-tune | 位置長文脈、量子予測 |
| TiRex | zero-shot quantile | Linux GPU、確率予測 |
| Moirai/Moirai-2 | zero-shot/fine-tune | 汎用確率 |
| Sundial | generative | ensemble多様性 |
| Kairos | research | 適応tokenization |
| Time-MoE/Timer系 | research | 大型比較、後回し |

## 5. モデルタスク表現

同じモデルでも3つの表現を別trialとして扱う。

1. Position regression: 7系列を次回値として予測。
2. Candidate binary/ranking: 37候補の次回出現確率・順位を予測。
3. Joint structured: 7位置分布と37候補分布を同時推定。

多変量専用モデルは正式主トラックから外し、外生変数・shared encoder研究トラックでのみ利用する。

## 6. モデルレジストリ必須属性

| 属性 | 例 |
|---|---|
| model_id | `nf-auto-nhits` |
| library | `neuralforecast` |
| package_version | `3.x pinned` |
| source_revision | Git commit/HF revision |
| license | Apache-2.0等 |
| task | position/candidate/joint |
| modes | train/zero-shot/fine-tune/embedding |
| capabilities | probabilistic, exog, multiseries, GPU |
| data_contract | long-v1/candidate-v2 |
| resource_profile | CPU, RAM, VRAM, timeout |
| adapter_version | semantic version |
| status | discovered/smoke/validated/shadow/champion/blocked |

## 7. 探索空間

- window: 10/30/100/all、指数減衰
- lag: 1..52から事前定義セット
- learning rate、hidden size、layers、dropout
- loss: MAE/MSE/Huber/Distribution/Quantile
- calibration: identity/Platt/temperature/isotonic/conformal
- decoder weights: candidate/position/theory
- residual: none/ridge/lightgbm/drift
- seed: 1 smoke、3 candidate、5 ambiguous、10 certification

## 8. モデル失格条件

- 非決定的設定を記録できない
- 将来情報を要求する
- revision/license不明
- timeout/OOMが予算を超える
- GPU要求なのにGPU証跡なし
- save/load後に予測不一致
- NaN/Inf、違法数字、確率不正
- outer foldの半数以上でBaseline未満かつ改善根拠なし
