# Loto Forecast Platform v2.0 最終実装検証

## 結果

- Python compileall: PASS
- 自動テスト: 47件 PASS
- Strict config validation: PASS
- Model catalog runtime export: PASS
- Research smoke: 5モデル、2 outer folds、失敗0
- Fixed holdout: 20抽選を未参照のまま隔離
- Leaderboard/Trial/Fold/Failure/Availability成果物: PASS
- UI/API v2 endpoints: TestClient PASS

## 実装済み

- 宣言型Model Registry（統計、ML、Nixtla、AutoML、TSFM）
- Optional dependency availability診断
- Strict YAMLとresolved config/hash
- Candidateモデル共通Runtime
- StatsForecast/MLForecast/NeuralForecast/AutoGluon/Darts/Chronos Worker
- Provider Job Contract（TimesFM/TTM/TiRex/Moirai/Sundial等）
- Outer/Inner rolling split、gap、fixed holdout、multi-seed
- Optuna/Ray探索、探索空間、Pruner/Sampler、fractional GPU資源
- 詳細±1指標、Hits、MAE/MSE、Brier、LogLoss、ECE、複合スコア
- OOF非負制約Ensemble
- Worker timeout/subprocess isolation
- MLflow、Prometheus、Grafana、Loki、Tempo、Ray Compose
- Model/Leaderboard UI/API

## 実機認定が必要

- RTX 5070 TiでのCUDA trial証跡
- 各上流モデル重みのdownload/license/revision固定
- StatsForecast/MLForecast/NeuralForecast全候補の長時間探索
- TimesFM/TTM/TiRex/Moirai/Sundial provider pluginの各上流版との互換確認
- 固定Holdoutと将来Shadowの承認付き解放

未導入・非互換モデルは成功扱いにせず、UNAVAILABLE/FAILEDとしてfailed_trialsへ記録する。
