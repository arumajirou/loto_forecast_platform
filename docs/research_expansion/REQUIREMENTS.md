# Requirements

## Functional Requirements

### FR-001 Research Source Intake

各候補は実装開始前に、logical `model_id`、paper、official source/model repository、source/model revision、file inventory、size、SHA-256、package/version、Python/Torch/Transformers compatibility、code/weight license、`trust_remote_code`、commercial eligibility、pretraining disclosure、contamination riskを固定する。不明値は`UNKNOWN`、`UNPINNED`、`UNVERIFIED`とし、推測で埋めない。

### FR-002 Provider Contract

各providerはdynamic `GameGeometry`、5ゲーム、horizon 1/2/5、position-univariate、正式対応する場合のみpanel/joint、context制約、point/quantile/sample意味、finite、shape、series identity、chronology、CPU fallback、fail-closed responseを持つ。

### FR-003 Runtime Certification

#123の共通SDKを使用し、package/model identity、checkpoint pre-load verification、load、input、inference、shape、finite、parameter/input/output device、provider PID、GPU PID/UUID/VRAM、no fallback、save/reload、別process replay、manifest、SHA256SUMS、REAL evidence originを証明する。fixtureやfakeはformalへ昇格させない。

### FR-004 Evaluation

最優先はHit@±1。必須併記はposition/all-position Hit@±1、MAE、MSE、RMSE、確率モデルのPinball、CRPSまたはEnergy Score、coverage、width、seed平均・母分散・最小・最大・worst、fold平均・worst fold。

必須baselineはRandom、fixed、mean、median、last、frequency、seasonal naive、AR等の統計モデル、同等以下の計算量を持つ軽量baseline。

### FR-005 Chronology and Leakage

- Train → Validation → Holdout → Prospective
- Scaler、Encoder、特徴量選択、HPOはTrain内
- OOFはexpanding chronological
- retrieval indexは各foldのTrainだけ
- causal graph/covariate選択もTrainだけ
- online updateはactual到着後
- Raw上書き禁止
- #124 Data Access Ledger接続

### FR-006 Prediction Lock

prediction payload、config/data/code/model revision hash、forecast origin、UTC lock timestampを保存し、`actuals_known_at_lock=false`、`actuals_included=false`を要求する。lock後の再予測を禁止する。

### FR-007 Reproducibility

Run ID、config、data/code hash、Git commit、model ID/revision、package versions、seed、fold、prediction、actual、metrics、logs、GPU/CPU、runtime evidence、manifest、SHA256SUMSを保存する。

### FR-008 Fair Compute

dataset、cutoff、fold、seed、trial/wall-time budget、CPU/GPU、context、horizon、postprocess、baseline、calibrationを一致または別protocolとして扱う。

### FR-009 Legal Output Constraints

Numbers3/4は各位置から1値。MiniLoto/Loto6/Loto7は固定cardinality、domain、重複禁止、昇順を守る。rawとreconciledを両方保存する。

### FR-010 Production Separation

source、contract、dependency、load、CPU、GPU、OOF、Holdout、Prospective、registry、productionを独立状態にする。`available=true`だけで昇格しない。

## Non-Functional Requirements

- main直接変更、force push、auto-merge、自動Holdout開封、自動promotion禁止
- uv、pyproject、uv.lock、src、tests、Ruff、mypy、pytest、coverage、Pydantic v2
- 競合依存はisolated environment
- GPU jobは1、CPU並列は安全範囲で最大8
- fallbackをsuccess扱いしない
- 全状態遷移とapprovalを監査可能にする
- 各PRは独立revert可能にする
