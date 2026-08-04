# Numbers3 N1 TCN 全引数検証設計

## 1. 目的

TCNの有限探索空間について全組合せを漏れなく実行し、
指定引数がモデル生成直後・学習後・保存再読込後にも反映されているか検証する。

## 2. モデル選定

TCNを選定する。直近50点ローリングでは候補6モデル中で以下の成績だった。

- MAE 2.420
- MSE 8.660
- Hit@±1 36.0%
- exact 14.0%

MAE基準2.560とHit@±1基準32.5%を同時に上回った唯一の候補である。
ただし50点だけなのでchampion認定ではなく、次段階の有望候補とする。

## 3. 「全引数」の定義

TCNコンストラクタの公開引数を`inspect.signature(TCN.__init__)`で取得する。
各引数を必ず次へ分類する。

1. search
2. fixed
3. runtime
4. excluded
5. default

未分類引数が存在した場合、ライブラリ更新による契約driftとして停止する。

## 4. 「全組合せ」の定義

YAMLに定義した有限候補集合のデカルト積を全件列挙する。
連続値全体、任意長リスト全体は無限なので対象にしない。

初期探索の組合せ数は次式で決まる。

```text
3 input_size
× 2 encoder_hidden_size
× 2 context_size
× 2 decoder_hidden_size
× 2 kernel_size
× 2 dilations
× 2 learning_rate
× 2 scaler_type
× 2 batch_size
= 768 combinations
```

各組合せを3 seed、10ローリング点で正式実行すると23,040 fitとなる。
初回はinventory、construct、8組合せ×2点smokeの順で検証する。

## 5. データ分割

- 時系列順序を保持
- 最後のrolling_pointsだけを逐次評価
- 各予測時点tでは0..t-1のみで学習
- Holdout/Prospectiveは別契約として封印
- scalerはモデル内部で各学習履歴だけにfit

## 6. 指標

主指標:

- Hit@±1

併記:

- MAE
- MSE
- RMSE
- exact
- seed平均
- seed標準偏差
- seed最悪値
- fit時間
- predict時間
- peak VRAM

## 7. 引数反映検証

### 生成直後

requestedとmodel属性またはhparamsを比較する。

### 学習後

`nf.models[0]`の属性とhparamsを再取得する。

### 保存再読込後

- `NeuralForecast.save`
- `NeuralForecast.load`
- 再予測
- 元予測との絶対誤差1e-6以内
- 成果物SHA-256

### 判定

- VERIFIED
- PROPERTY_MISMATCH
- NOT_EXPOSED
- CONSTRUCTOR_ERROR
- FIT_ERROR
- LOAD_ERROR
- PREDICTION_MISMATCH

## 8. GPU認定

以下を保存する。

- CUDA available
- GPU name
- PID
- model parameter devices
- output finite
- peak allocated VRAM
- CPU fallback=false
- fit/predict時間

## 9. 採用条件

最良seed単独では採用しない。

1. Hit@±1平均
2. Hit@±1最悪seed
3. MAE平均
4. MSE平均
5. RMSE平均
6. 計算資源

Holdoutは探索終了後、設定を固定しSHA-256で凍結してから一度だけ使用する。
