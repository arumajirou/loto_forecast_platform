# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. リポジトリ構造

```text
loto/
  pyproject.toml
  uv.lock
  configs/
  schemas/
  src/loto/
    data/
    features/
    datasets/
    models/
      registry/
      adapters/
      workers/
      baselines/
    search/
    evaluation/
    calibration/
    residuals/
    ensembles/
    decoding/
    orchestration/
    registry/
    observability/
    sealing/
    api/
    ui/
    security/
  workers/
    nixtla/
    autogluon/
    darts/
    gluonts/
    hf_tsfn/
  deploy/
  tests/
  docs/
```

## 2. 主要型

```python
class ModelRequest(BaseModel):
    run_id: str
    trial_id: str
    model_id: str
    task: Literal['position','candidate','joint']
    train_dataset_uri: str
    validation_dataset_uri: str | None
    config: dict
    seed: int
    resource_limits: ResourceLimits

class ModelPrediction(BaseModel):
    trial_id: str
    forecast_origin: datetime
    candidate_probabilities: list[float] | None
    position_distributions: list[list[float]] | None
    point_positions: list[float] | None
    quantiles: dict[str, list[float]] | None
    provenance: Provenance

class TrialResult(BaseModel):
    metrics: MetricBundle
    resource_evidence: ResourceEvidence
    artifact_uris: dict[str,str]
    status: Literal['OK','FAILED','PRUNED','DISQUALIFIED']
```

## 3. Worker RPC

HTTP/gRPCのどちらでも実装可能だが、初期はFastAPI + JSON + Artifact URIを採用する。大規模配列を本文に送らずParquet/Arrow URIで受け渡す。

| Endpoint | 操作 |
|---|---|
| `GET /health` | 依存・GPU・モデルキャッシュ確認 |
| `GET /capabilities` | 対応モデル・タスク・資源 |
| `POST /jobs/fit-predict` | 非同期trial開始 |
| `GET /jobs/{id}` | 状態取得 |
| `POST /jobs/{id}/cancel` | 中断 |
| `POST /models/load` | 事前ロード |
| `POST /models/unload` | VRAM解放 |

## 4. Nested Rolling CVアルゴリズム

```python
for outer_fold in outer_splitter(dev_region):
    inner_train = outer_fold.train
    study = create_optuna_study(direction='maximize')
    for trial in study:
        cfg = sample_model_and_hyperparams(trial)
        scores = []
        for inner_fold in inner_splitter(inner_train):
            pred = run_model(cfg, inner_fold, seed)
            scores.append(composite_inner_objective(pred))
        trial.report(robust_aggregate(scores))
    best_cfg = select_stable_config(study)
    for seed in certification_seeds:
        outer_pred = run_model(best_cfg, outer_fold, seed)
        persist_outer_prediction(outer_pred)
```

inner objectiveは違法/リークを先に失格、校正Gate通過後にHits@7、±1、安定性を用いる。Holdoutは全Outer比較とモデル凍結後に一度だけ実行する。

## 5. GPU証跡

trial開始前・学習中・終了後に収集する。

- nvidia-smi query: UUID、PID、VRAM、util、temperature、power
- PyTorch: `cuda.is_available`、device、allocated/reserved/max_memory
- Worker PIDとGPU compute processの照合
- 学習中サンプラーを5秒間隔、短trialは高頻度モード
- `peak_vram_mib=0`またはPID不一致ならGPU trial失格
- CPU trialはGPU非利用を正常として明示

## 6. 並列化

| レベル | 技術 | 制御 |
|---|---|---|
| データ | Polars/PyArrow、multiprocessing | ゲーム・partition単位 |
| 統計モデル | StatsForecast n_jobs/Ray | series/fold単位 |
| ML | LightGBM threads、Ray | trial/fold単位 |
| DL | 1 GPU 1 heavy trial、軽量はfractional | VRAM予約ベース |
| TSFM | model server + batch | 同一revisionを共有ロード |
| 評価 | Ray tasks | prediction artifact単位 |

RTX 5070 Ti 16GBでは、同時に複数大型GPU trialを走らせず、`GPUResourceBroker`がVRAM見積と実測を使ってキュー制御する。

## 7. キャッシュ・効率化

- Raw/Canonical/Feature/Datasetをcontent hashで再利用
- fold datasetはArrow memory map
- 同一モデルrevisionのtokenizer/weightsをworker内共有
- zero-shot予測をseries hashでキャッシュ
- outer foldはinner成果物を再利用しない（リーク防止）
- pruning: median/ASHA、ただし短foldでは過剰prune禁止
- mixed precisionはモデル別allowlist
- compile/flash attentionは再現性検証後に有効化

## 8. 校正・残差・Ensemble

1. inner OOF予測を収集
2. 校正候補をfitしinner validationで選択
3. 残差補正器をOOFのみでfit
4. 各モデルのouter予測を保存
5. outer OOF相当の予測から非負重みを学習
6. 重み合計1、上限0.60、fold間変動制約
7. theory decoderをshrinkage先として常に比較

## 9. デコーダ

- Stage A: candidate確率とposition分布を校正
- Stage B: DPで昇順7数字のTop-Kを生成
- Stage C: 非加法特徴（連番、レンジ、重複末尾等）でrerank
- Stage D: 多様性制約付き複数候補を任意出力
- 公式1組は最高スコアのみ封印

## 10. 状態機械

```text
CREATED -> DATA_READY -> SEARCHING -> OUTER_EVALUATING
-> FROZEN -> HOLDOUT_PENDING -> HOLDOUT_EVALUATED
-> SHADOW -> APPROVAL_PENDING -> PROMOTED -> RETIRED
```

失敗時は`FAILED_RETRYABLE`、`FAILED_TERMINAL`、`DISQUALIFIED`を区別する。

## 11. DB主要テーブル

- runs, stages, trials, folds, seeds
- models, model_versions, capabilities
- datasets, feature_sets, manifests
- predictions, metrics, position_metrics
- gpu_samples, resource_summaries
- optuna_studies, trial_params
- releases, champions, approvals
- sealed_forecasts, shadow_scores
- audit_events, alerts

## 12. セキュリティ

- Secretは環境変数/Secret Store、ログへ出さない
- Workerはallowlistモデルのみ取得
- Hugging Face `revision`をcommit hashで固定
- `trust_remote_code`は原則禁止、例外承認制
- safetensors優先、pickle artifactは隔離
- SBOM、署名OCI、依存脆弱性スキャン
