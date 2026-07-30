# Stage 2モデル再評価・設定反映検証報告

## 1. 概要

本資料は、LOTO7時系列予測モデルのGPU探索キャンペーンからStage 2再評価候補を選定し、モデル設定、保存成果物、精度指標、CV構成および実行制御を検証した結果を記録する。

- 作成日: 2026-07-31
- 対象: `loto_forecast_platform`
- 対象キャンペーン: `runs/gpu-24h-campaign/20260731-012917`

## 2. GPU探索キャンペーン

確認時点:

| 項目 | 値 |
|---|---:|
| 総試行数 | 3,463 |
| 成功 | 942 |
| 失敗 | 0 |
| タイムアウト | 0 |
| 未実行 | 2,520 |
| 進捗率 | 27.20% |
| 終了期限（UTC） | 2026-07-31 16:29:18 |
| 終了期限（JST） | 2026-08-01 01:29:18 |

単一GPU上でGPUキャンペーンとStage 2を同時実行しない。

## 3. 厳格な成功判定

ラッパーの終了コード0だけでなく、以下を満たす試行を検証済みとする。

- trial stateとYAMLのモデルパラメータが一致
- checkpointまたは正式保存モデルが存在
- `research_summary.json`が存在
- `position_mae`が存在
- `position_mse`が存在
- `mean_within_1`が存在
- fold結果が存在

確認済みの中間集計:

| 分類 | 件数 |
|---|---:|
| ラッパー成功 | 866 |
| 厳格検証済み | 263 |
| 不完全または未検証 | 603 |
| 厳格検証率 | 30.37% |

## 4. 結果ファイルの重複検証

非空の予測・評価関連ファイル538件をSHA-256で比較した結果、完全重複グループは0件だった。

以前検出された同一ハッシュは、改行のみなど実質的に空のCSVに由来する。異なるモデル設定が大量に同一予測を生成した証拠ではない。

## 5. Stage 2候補

Stage 2候補は12件。

| モデル | 件数 |
|---|---:|
| VanillaTransformer | 2 |
| TSMixer | 2 |
| TCN | 2 |
| TFT | 1 |
| TiDE | 2 |
| DLinear | 2 |
| NLinear | 1 |
| 合計 | 12 |

候補一覧は実行成果物側の`stage2-final-12.csv`で管理し、Gitには原則登録しない。

## 6. Stage 2データ

現在の候補設定は次を参照している。

```text
examples/sample_loto7.csv
```

有効行数は160行。

このデータは動作検証、seed安定性、設定反映確認、小規模モデル比較には使えるが、正式な性能確定には使用しない。

## 7. 修正後のCV構成

| 設定 | 値 |
|---|---:|
| `min_train_size` | 100 |
| `holdout_size` | 16 |
| `outer_folds` | 10 |
| `test_size` | 4 |
| 評価対象/seed | 40 |
| seeds | 42, 43, 44 |
| 評価実行単位/モデル | 120 |
| 必要行数 | 156 |
| 安全余白 | 4 |

算術条件:

```text
100 + 16 + 10 × 4 = 156
160 - 156 = 4
```

12設定すべてでCV算術検証および設定スキーマ検証に合格した。

## 8. 旧Stage 2失敗の原因

旧設定:

```text
min_train_size = 300
holdout_size   = 40
outer_folds    = 10
test_size      = 10
```

必要行数:

```text
300 + 40 + 10 × 10 = 440
```

入力は160行のため、outer foldを構築できなかった。

発生したエラー:

```text
ValueError: no outer folds can be constructed;
reduce holdout/test size or min_train_size
```

これはGPU障害、VRAM不足、モデル実装不良、精度不良、パラメータ未反映を原因としない。CV分割条件と入力行数の不整合が原因である。

## 9. Stage 2実行制御

実行条件:

1. 対象GPUキャンペーンの親プロセス終了
2. キャンペーン配下の研究子プロセス終了
3. Stage 2が未起動
4. GPUが他用途で占有されていない
5. CV算術条件が成立
6. 設定スキーマ検証済み

成功条件:

- 終了コード0
- `research_summary.json`が存在
- `champion.position_mae`が存在
- `champion.position_mse`が存在
- `champion.mean_within_1`が存在

不足時は`PARTIAL_NO_METRICS`として扱う。

## 10. 正式評価への移行

Stage 2終了後:

1. MAE、MSE、RMSE、±1率、全7位置±1率を集計
2. seed間平均・標準偏差・信頼区間を算出
3. 上位3〜5候補を選定
4. 実LOTO7全687抽選以上へ切り替え
5. walk-forward評価
6. 完全未使用holdout評価
7. 位置別中央値、expanding median、last value、制約付きランダムと比較
8. prospective評価へ移行
