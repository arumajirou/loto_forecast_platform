# モデルパラメータ反映・精度検証設計

## 1. 目的

設定値がファイルへ保存されただけでなく、モデル生成、学習、保存、推論、評価へ実際に反映されたことを証明する。

## 2. 証跡レイヤー

### 2.1 要求設定

確認対象:

- campaign state
- trial params
- trial YAML
- config hash

判定:

```text
state params == YAML model_params
```

### 2.2 モデル生成

確認対象:

- コンストラクタ引数
- 解決済み引数
- `configuration.pkl`
- checkpointの`hyper_parameters`
- モデルクラス
- ライブラリ名とversion

判定:

```text
requested params == resolved params
requested params == checkpoint hyper_parameters
```

内部で別名へ変換される引数はマッピングを保存する。

### 2.3 学習実行

記録対象:

- seed
- fold
- start/end
- epoch
- global step
- early stopping
- device
- precision
- CUDA availability
- GPU利用率
- VRAM
- power
- elapsed time
- exit reason

`max_steps`は上限であり、早期停止時の`global_step`と一致しないことがある。

### 2.4 成果物

最低限:

- `research_summary.json`
- `trial_results.csv`
- `fold_results.csv`
- checkpointまたは正式保存モデル
- config hash
- ログ
- リソース記録

### 2.5 精度

主要指標:

- position MAE
- position MSE
- position RMSE
- mean within ±1
- all positions within ±1
- mean hits at 7
- Brier score
- log loss
- ECE
- composite score

## 3. ステータス

### SUCCEEDED_VERIFIED

- 終了コード0
- 設定一致
- 成果物あり
- 主要指標あり
- fold結果あり

### PARTIAL_NO_CHECKPOINT

- 精度指標あり
- checkpointなし

### PARTIAL_NO_METRICS

- 学習または保存完了
- 主要指標なし

### FAILED

- 実行例外

### TIMEOUT

- 制限時間超過

## 4. パラメータ効果分析

モデルごとに、各値の件数、平均、標準偏差を集計する。

対象例:

- input size
- batch size
- learning rate
- max steps
- hidden size
- layers
- dropout
- scaler
- context size
- kernel size
- dilations

list/dict/tupleは正規化JSON文字列へ変換し、Pandasのgroup keyとして利用する。

## 5. 交絡への対応

単純なパラメータ別平均は因果効果ではない。

正式分析:

1. 同一モデル内比較
2. 同一fold
3. 複数seed
4. 他条件固定比較
5. fANOVA
6. permutation importance
7. bootstrap confidence interval
8. 多重比較補正

## 6. 再現性

保存対象:

- Git commit hash
- config hash
- data hash
- Python version
- package lock
- CUDA version
- driver version
- GPU名
- seed
- fold境界
- command line
- environment variables
- timestamps
- timezone

## 7. データリーク防止

禁止:

- 未来情報の学習混入
- holdoutの探索利用
- 同一抽選の区分重複
- 時系列のランダムシャッフル
- 全期間前処理後の分割
- テスト期間を用いたハイパーパラメータ選定

推奨:

- expanding window
- rolling origin
- 完全未使用holdout
- prospective評価
- baselineとの同一期間比較

## 8. ベースライン

最低限:

- 位置別中央値
- expanding median
- last value
- seasonal naive
- 頻度ベース
- 制約付きランダム
- 固定予測
- 線形モデル

## 9. 正式採用基準

- 複数seedで再現
- 複数foldで安定
- 独立holdoutで改善
- baselineを改善
- データリークなし
- 設定証跡が完全
- GPU使用証跡が完全
- 成果物再現可能
- 推論コストが運用可能
