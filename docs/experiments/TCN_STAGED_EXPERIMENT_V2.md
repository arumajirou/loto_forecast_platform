# TCN段階型実験設計 v2

## 因子分類

精度因子:
- input_size
- encoder_hidden_size
- context_size
- decoder_hidden_size
- kernel_size
- dilations
- learning_rate
- scaler_type

計算資源因子:
- windows_batch_size
- precision
- deterministic / benchmark

固定:
- h=1
- batch_size=32
- valid_batch_size=None
- inference_windows_batch_size=-1

nuisance:
- seed
- rolling test index

## Phase 1 screening

基準設定から1因子だけ変える paired OFAT。
同じseed・同じ予測時点で差を測る。

## Phase 2 interaction

screeningで有望だった2〜4因子だけ完全要因化する。

## Phase 3 confirmation

上位16候補を3 seed、30 rolling points以上で比較。

## Phase 4 certification

上位3候補だけ保存・再読込・SHA-256・GPU証跡を確認。
