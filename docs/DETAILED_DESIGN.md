# 詳細設計書

## 共通契約

`DatasetManifest`, `FeatureSetManifest`, `CandidateProbability`, `PositionProbability`, `DecodedCombination`, `ForecastPackage`, `EvaluationReport`, `PromotionDecision`をPydanticで定義し、未知キーを拒否する。

## Canonical検査

- 必須列: draw_no, draw_date, n1..n7
- draw_no重複禁止
- 数字は1..37、7個、厳密昇順
- 決定論的DataFrameハッシュ

## 特徴量

対象抽選の特徴量は必ず`master.iloc[:idx]`から生成する。現在抽選のselectedを特徴量計算へ入れない。窓10/30/100、全履歴、指数減衰、gapを初期実装とする。

## デコーダ

位置`p`、最後の数字`n`を状態とする動的計画法。各状態にtop-k経路を保持し、7位置目で全経路を集約する。出力は必ず7個・昇順・重複なし。

## 評価

集合Hitsは抽選単位で集合積を計算。bootstrapは抽選行を再標本化し、位置を平坦化しない。Brier/Log Loss/ECEは37候補確率で計算する。

## 昇格

+0.10を暫定、+0.15を正式効果量とし、校正非劣性、fold過半数、bootstrap下限>0、Shadow件数をゲート化する。証拠不足は`CONTINUE_EVALUATION`。

## 封印

予測payloadをcanonical JSON化しSHA-256を計算、HMAC-SHA256で署名する。評価結果は元payloadを変更せず別Artifactへ追記する。

## NeuralForecast Adapter

`AutoModelRequest`を`AutoModelPlan`へ解決する。early stoppingはmodel configへ配置し、実行層のworker設定をモデルへ盲目的に渡さない。TSMixer系のn_series、TimesNet FFT精度制約を事前検査する。
