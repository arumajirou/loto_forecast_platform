# 要件定義書

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## 1. 目的

数字選択式くじ・数字ゲームを対象に、データ取得、特徴量生成、学習、評価、再学習、予測固定、運用監視までを再現可能かつ監査可能な時系列予測研究基盤として提供する。

現在の共通ゲームgeometryは `loto.game.geometry` を正本とし、少なくとも次を扱う。

```text
mini
loto6
loto7
bingo5
numbers3
numbers4
```

目的は見かけ上の最良seedや単一モデルの最大値を作ることではなく、同一の科学契約で比較可能な証拠を生成することである。

## 2. 最優先成功指標

正式な主指標は **Hit@±1** とする。

必須併記指標:

- MAE
- MSE
- RMSE
- 位置別 Hit@±1
- 全位置 Hit@±1

必要に応じて確率予測・ランキング・集合指標を追加してよいが、主指標を置換してはならない。

## 3. 必須ベースライン

同一のeligible fold / seed / actualで、最低限次を常時比較する。

1. Random
2. 固定値
3. 平均
4. 中央値
5. 直近値
6. 頻度
7. 統計モデル

Unified campaignでは統計モデルの基準として `statistical_ar1` を使用する。

## 4. 時系列分割とリーク防止

時間順に次を分離する。

```text
Train -> Validation / OOF development -> Holdout -> Prospective
```

必須要件:

- Scaler、Encoder、特徴量選択、HPOはeligible Train内だけでfitする。
- foldの未来情報を前処理・特徴量・探索に混入させない。
- 欠損、重複、順序違反、domain違反、future-derived featureを検査する。
- Holdoutはdevelopment/OOFの承認前に開かない。
- Prospectiveは対応する実測が存在する前に予測を固定する。
- rawデータは不変正本とし、上書きしない。

## 5. Multi-seed要件

探索・評価は承認されたseed inventoryを保持する。

最低限保存する集約:

- count
- mean
- population variance
- standard deviation
- minimum
- maximum
- worst value
- worst seed

最良seedだけを採用根拠にしてはならない。

## 6. 予測固定要件

実測を読む前に予測artifactを永続化し、SHA-256と時刻で固定する。

Unified campaignでは各 `game × candidate × seed` について、`actuals_known=false` のprediction lockをwrite/fsyncし、SHA-256を計算した後にのみ対応actualをscoring段階で読む。

既存run directoryは再利用・上書きしない。

## 7. モデル比較要件

公平な条件で比較対象を区別する。

- 単変量
- 外生変数付き
- 位置別モデル
- 共有モデル
- アンサンブル
- foundation/TSFM provider
- candidate estimator
- reconciliation / calibration / post-processing method

`174 registered` のようなcatalog countを、174個の独立forecaster、174個のshared-routable model、174個のruntime-certified model、174個のOOF済みmodelと読み替えてはならない。

Unified campaignはrequested broad-catalog × gameのcoverage rowを必ず作り、非対応・非route・runtime失敗も明示的statusで残す。

## 8. Decoder要件

select-gameの合法性を保持し、digit-gameの順序と重複を壊さない。

Merged PR #249/#250により、確率を持つunified candidate routeはfamily-specific `WITHIN_TAU` decodingを使用する。

- select family: legality制約付きWITHIN_TAU DP
- digit family: positional window-mass WITHIN_TAU decoding
- point-only worker: 確率分布を捏造せずpoint legalisationを継続

Decoder実装の理論最適性テストは実データOOF改善の証明ではない。

## 9. Runtime certification要件

「catalogにある」「dependencyがinstallできる」だけで成功にしない。

正式runtime evidenceでは該当する範囲で次を検証する。

- model load
- input construction
- inference completion
- output shape
- finite values
- requested/observed device
- GPU PID
- VRAM
- CPU fallback
- reload inference / persistence reproducibility
- model revision / artifact hash / code hash / environment identity

Runtime certificationはforecast accuracyを証明しない。

## 10. Python・品質要件

原則:

```text
uv
pyproject.toml
uv.lock
src/
tests/
```

品質ツール:

- Ruff
- mypy
- pytest
- pytest-cov
- Pydantic

実装中はfocused testとsmokeを優先し、重いfull pytest / GitHub CIは変更がまとまった最終ゲートで実施する。

## 11. 実験証跡要件

各実験にRun IDを発行し、可能な範囲で次をPostgreSQL、DuckDB、Parquet、MLflow等へ保存する。

- config
- data hash
- code hash
- Git commit
- model ID / revision
- seed
- predictions
- actuals
- metrics
- logs
- runtime/device/GPU情報
- protocol identity
- prediction lock evidence

## 12. Unified campaign受入要件

`uv run loto3 campaign --output unused --plan-only` がrequested model × game matrixをmaterializeできること。

実行時は最低限:

- six-game geometryに従うこと
- 必須7 baselineを評価すること
- Hit@±1をprimaryにすること
- 全seed evidenceを残すこと
- prediction sealをactual access前に作ること
- output directoryを上書きしないこと
- unsupported/unavailable/failed rowを黙って消さないこと
- Holdout/Prospectiveを開かないこと

## 13. 科学的昇格要件

実装完了、runtime success、OOF success、Holdout success、Prospective success、promotionは別段階である。

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
```

後段の状態を前段から推測してはならない。`champion=null` は有効な正式結果である。

## 14. 現在の非主張

この要件定義書は以下を主張しない。

- 全174登録entryが全6ゲームで成功した
- 実データ174 × 6 campaignが完了した
- WITHIN_TAU decoderが実OOFを改善した
- Holdoutが開かれた
- Prospectiveが完了した
- championが存在する
- production promotionが承認された
