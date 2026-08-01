# Numbers3 N1 決定論ローリング評価 引き継ぎ資料

作成日: 2026-08-02  
対象リポジトリ: `loto_forecast_platform`  
対象系列: Numbers3 N1  
GPU: NVIDIA GeForce RTX 5070 Ti 16GB  
評価方式: 単変量、h=1、ローリング評価

## 1. 目的

Numbers3 N1について、NeuralForecastモデルを比較し、以下を満たす候補を特定する。

- digit MAE基準 `2.560` を下回る
- ±1率基準 `32.5%` を上回る
- GPU上で学習と予測を実行する
- VRAM、GPU使用率、温度、電力を記録する
- 並列化により高速化する
- 同一設定で再現可能にする

## 2. 完了した作業

1. 23モデルの固定起点200ステップ評価
2. 上位6モデルのh=1ローリング50点評価
3. DeepARの確率予測列選択修正
4. モデル単位の独立worker実装
5. VRAM監視付きスケジューラ実装
6. 評価点のシャード並列化
7. PyTorch決定論設定
8. cuBLAS決定論設定
9. 決定論スモークテスト2回
10. 決定論50点本番
11. 過去結果との300行回帰比較

## 3. 最終結果

| 順位 | モデル | digit MAE | digit MSE | ±1率 | 完全一致率 |
|---:|---|---:|---:|---:|---:|
| 1 | TCN | 2.420 | 8.660 | 36.0% | 14.0% |
| 2 | KAN | 2.520 | 9.040 | 30.0% | 16.0% |
| 3 | NLinear | 2.580 | 9.420 | 26.0% | 8.0% |
| 4 | Informer | 2.600 | 9.640 | 28.0% | 14.0% |
| 5 | TimesNet | 2.620 | 9.500 | 30.0% | 8.0% |
| 6 | MLP | 2.640 | 10.040 | 34.0% | 8.0% |

## 4. 現在の最良候補

`TCN`

- digit MAE: `2.420`
- digit MSE: `8.660`
- ±1率: `36.0%`
- 完全一致率: `14.0%`
- MAE改善率: 約`5.47%`
- ±1率改善幅: `+3.5ポイント`

TCNは、digit MAE基準と±1率基準を両方上回った唯一のモデルである。

## 5. 再現性

### 決定論スモーク

同じ設定で6評価点を2回実行した。

- 比較行数: 36
- raw予測差: 0
- 整数予測差: 0
- 判定: `BITWISE_REPRODUCIBLE`

### 決定論50点と過去結果

- 比較行数: 300
- raw予測最大差: `0.011716604232788086`
- 整数予測変更行: 0
- ±1判定変更行: 0
- 完全一致判定変更行: 0

整数化後の予測と評価指標は再現されている。

## 6. 正式並列設定

- `max-workers=8`
- `reserve-mib=2500`
- `poll-seconds=0.5`
- Informer: 3シャード
- TimesNet: 2シャード
- KAN: 2シャード
- TCN: 2シャード
- NLinear: 1シャード
- MLP: 1シャード

合計11ジョブ。

## 7. 決定論設定

worker:

- `torch.manual_seed(SEED)`
- `torch.cuda.manual_seed_all(SEED)`
- `torch.backends.cudnn.benchmark = False`
- `torch.backends.cudnn.deterministic = True`
- `torch.use_deterministic_algorithms(True, warn_only=True)`

スケジューラ環境変数:

- `CUBLAS_WORKSPACE_CONFIG=:4096:8`
- `PYTORCH_ALLOC_CONF=expandable_segments:True`
- `OMP_NUM_THREADS=2`
- `MKL_NUM_THREADS=2`
- `OPENBLAS_NUM_THREADS=2`
- `NUMEXPR_NUM_THREADS=2`

## 8. 追加した主要ファイル

- `scripts/experiments/run_numbers3_n1_nf_phase1.py`
- `scripts/experiments/run_numbers3_n1_nf_phase2.py`
- `scripts/experiments/run_numbers3_n1_nf_phase3.py`
- `scripts/experiments/run_numbers3_n1_deepar_only.py`
- `scripts/experiments/run_numbers3_n1_tft_only.py`
- `scripts/experiments/run_numbers3_n1_rolling_top6.py`
- `scripts/experiments/run_numbers3_n1_rolling_worker.py`
- `scripts/experiments/run_numbers3_n1_vram_scheduler.py`
- `scripts/experiments/run_numbers3_n1_sharded_scheduler.py`

## 9. 主要成果物

成果物はローカル保存し、Gitには含めない。

- `artifacts/numbers3/n1_nf_23_model_ranking.csv`
- `artifacts/numbers3/n1_rolling_parallel/numbers3_n1_deterministic_50_detail.parquet`
- `artifacts/numbers3/n1_rolling_parallel/numbers3_n1_deterministic_50_summary.csv`
- `artifacts/numbers3/n1_rolling_parallel/deterministic_50_vs_original.csv`
- `artifacts/numbers3/n1_rolling_parallel/gpu_monitor.csv`
- `artifacts/numbers3/n1_rolling_parallel/scheduler_status.csv`
- `artifacts/numbers3/n1_rolling_parallel/scheduler.log`

## 10. テスト状況

Python構文検査:

- 対象スクリプトすべてPASS

pytest:

- 約47%まで進行
- 失敗表示なし
- 手動で停止したため、全テスト完了とは判定しない

## 11. 次に実施する作業

1. TCNとKANを直近200点以上で評価
2. 複数期間fold評価
3. 複数seed評価
4. 同一期間baseline再計算
5. TCNハイパーパラメータ探索
6. 予測定数化検査
7. データリーク検査
8. prospective評価
9. 予測区間と校正評価

## 12. 注意事項

作業ツリーには今回と無関係な変更・未追跡ファイルが多数存在する。

今回のコミットではNumbers3 N1関連ファイルだけを明示的にstageし、以下を含めない。

- `data/`
- `artifacts/`
- `components/`
- `extensions/`
- `releases/`
- `configs/platform.env`
- Chronosや外生変数実験の既存変更
- `torch`
- `chronos`

## 13. 結論

現時点の正式候補はTCNである。

直近50点のh=1ローリング評価で、

- digit MAE `2.420`
- ±1率 `36.0%`
- 完全一致率 `14.0%`

を記録した。

決定論スモークではビット単位の再現性を確認し、50点評価でも整数予測と評価判定が全300行一致した。
