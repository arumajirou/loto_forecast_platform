# GPU 24-hour campaign v2

目的:

- Nixtla NeuralForecastモデルと基盤時系列モデル候補を24時間の時間予算で反復実行
- モデルごとに異なる有限パラメータ集合をランダム化して試行
- 設定不正・import不足・CUDA OOM・timeoutを隔離してキャンペーン継続
- 各runの設定、ログ、結果、モデル/checkpoint候補、SHA-256 manifestを保存
- `state.json`から再開可能
- GPU campaignの重複起動を`flock`で防止

## インストール

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
git rev-parse --show-toplevel

install -m 755 gpu_24h_campaign.py scripts/gpu_24h_campaign.py
install -m 755 run_gpu_24h_campaign.sh run_gpu_24h_campaign.sh

uv run python -m py_compile scripts/gpu_24h_campaign.py
bash -n run_gpu_24h_campaign.sh
```

## 起動

```bash
HOURS=24 \
PER_MODEL=200 \
TRIAL_TIMEOUT=7200 \
CPU_THREADS=8 \
PRECISION=32 \
./run_gpu_24h_campaign.sh
```

## 監視

```bash
LATEST="$(
  find runs/gpu-24h-campaign -mindepth 1 -maxdepth 1 -type d \
    -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-
)"
cat "$LATEST/summary.json" 2>/dev/null || true
tail -n 30 /mnt/e/env/ts/logs/gpu-24h-campaign-*.log
nvidia-smi
```

## 再開

```bash
uv run python scripts/gpu_24h_campaign.py \
  --resume-campaign runs/gpu-24h-campaign/<timestamp> \
  --hours 24
```

## 注意

- `model_catalog.json`に存在しても、依存パッケージやアダプタが未実装なら
  `INVALID_CONFIG`または`IMPORT_ERROR`として記録されます。
- underlying adapterがcheckpointを書き出した場合、`saved-models/<trial_id>/`へ収集します。
- モデルパラメータ名はNeuralForecastの世代差で変わる可能性があります。
  不正な組合せはキャンペーンを停止せず記録されます。
- 24時間「必ずGPU 100%」を保証するものではありません。小規模データではCPU前処理や
  subprocess起動が支配的です。重いTransformer/NHITS/TiDE系を多く含めることでGPU占有率を上げます。
