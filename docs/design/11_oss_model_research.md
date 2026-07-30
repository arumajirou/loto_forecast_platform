# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. 主要参照OSS（調査時点 2026-07-30）

| OSS | 採用理由 |
|---|---|
| Nixtla NeuralForecast | 多数のニューラルモデル、AutoModel、Ray/Optuna |
| Nixtla StatsForecast | 高速統計モデル、疎系列、確率予測 |
| Nixtla MLForecast | 高速ラグ特徴量、sklearn、Conformal、Ray |
| Nixtla HierarchicalForecast | BottomUp/MinTrace等の整合化 |
| AutoGluon TimeSeries | AutoML、Chronos-2、Ensemble |
| sktime | 統一API、分割・チューニング |
| Darts | 統一backtest、NeuralForecast/TSFM wrapper |
| GluonTS | 確率予測、DeepAR、TSFMデータ形式 |
| Optuna | HPO、pruning、RDB storage |
| Ray | 分散trial、resource scheduling |
| MLflow | 実験・model registry・artifact |
| OpenTelemetry | trace/log/metric相関 |
| Prometheus/Grafana/Loki/Tempo | 運用観測 |

## 2. 主要公開情報

- NeuralForecast: https://github.com/Nixtla/neuralforecast
- StatsForecast: https://github.com/Nixtla/statsforecast
- MLForecast: https://github.com/Nixtla/mlforecast
- HierarchicalForecast: https://github.com/Nixtla/hierarchicalforecast
- AutoGluon: https://github.com/autogluon/autogluon
- sktime: https://github.com/sktime/sktime
- Darts: https://github.com/unit8co/darts
- GluonTS: https://github.com/awslabs/gluonts
- GitHub time-series topic: https://github.com/topics/time-series
- Hugging Face time-series forecasting: https://huggingface.co/models?pipeline_tag=time-series-forecasting

## 3. ファクトチェック上の注意

- OSSのversion、モデル一覧、依存、licenseは実装開始時に再取得しcommit/revisionを固定する。
- GitHub Topic/Hugging Face検索結果は候補発見用であり、品質保証ではない。
- Darts等の統合wrapperは便利だが、同じ基底モデルを重複比較しないよう`canonical_model_family`を設定する。
- HierarchicalForecastはLoto7へ自動的に有効ではなく、加法的階層を明示し、元予測とのOuter CV比較で採否を決める。
