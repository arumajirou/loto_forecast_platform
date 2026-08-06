# Latest Forecasting Research Expansion — Full Implementation Blueprint v1

## Status

```text
DOCUMENTATION_ONLY
IMPLEMENTATION_NOT_STARTED
MAIN_BASE=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
HOLDOUT=NOT_OPENED
PROSPECTIVE=NOT_OPENED
REAL_MODEL_RUNTIME=NOT_EXECUTED
```

本資料群は、2025～2026年の時系列予測研究と公式公開実装を `loto_forecast_platform` へ追加するための、基本設計、詳細設計、実装計画、PR分割、実行工程、検証計画、リスク、出典、実行プロンプトを定義する。

この文書PRは設計専用であり、モデルコード、依存関係、`uv.lock`、workflow、Rawデータ、Holdout、Prospective、Registry、Runtime Certificationの挙動を変更しない。

## 目的

1. 公式論文、公式コード、公式weight、license、revisionを固定する。
2. 既存共通基盤を再利用し、モデル専用certifierや独自statusを増やさない。
3. Train／Validation／Holdout／Prospectiveを時間順に分離する。
4. Scaler、Encoder、特徴量選択、HPO、retrieval indexをTrain内だけで構築する。
5. Hit@±1を最優先とし、MAE、MSE、RMSE、位置別／全位置Hit@±1を併記する。
6. 複数seedの平均、分散、最悪値を保存し、最良seedだけを採用しない。
7. 予測を実測判明前にSHA-256と時刻で固定する。
8. load、input、inference、shape、finite、device、PID、GPU UUID、VRAM、CPU fallback、save/reload/replayを正式証拠で確認する。
9. 単純baselineを常に残し、改善がなければ`champion=null`を許容する。
10. 研究結果とproduction eligibilityを分離する。

## 対象

### Model Intake Wave

- Granite FlowState
- TempoPFN
- Kairos 10M／23M／50M
- Reverso-Small
- Granite PatchTST-FM
- LightGTS
- Super-Linear
- 調査対象: TimeFound、Xihe、YingLong、VisionTS、TimePro、KRNO

### Method Wave

- Retrieval-Augmented Forecasting: RAFT、TS-RAG
- Train-only Retrieval Index
- Covariate Adapter／causal screening
- Online／test-time adaptation
- Sample-conditioned adaptive ensemble
- Partition-matroid／one-per-position sampler
- Relational／online conformal
- Benchmark contamination registry
- GIFT-Eval／fev-style task fingerprintと効率評価

## 既存Draft PRとの責務分離

| 基盤 | 既存PR | 本設計での扱い |
|---|---:|---|
| Version single source | #120 | merge後に利用。再実装しない |
| Strict Configuration | #121 | 新campaignの設定基盤。再実装しない |
| Runtime Certification SDK | #123 | provider認証の共通基盤。専用certifierを増やさない |
| Data Access Ledger | #124 | retrieval／covariate／online処理のアクセス証拠に使用 |
| Provider別既存Draft | 多数 | 変更しない。新規候補は独立PRで導入 |
| Prediction／Actual／Registry監査 | 別担当 | 本文書PRでは実装しない |

## 非保証

全て実装してもHit@±1が改善する保証はない。複雑なモデルがRandom、平均、中央値、直近値、頻度、統計モデルを上回らない可能性を正式結果として受け入れる。
