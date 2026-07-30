# GPUキャンペーンからStage 2への運用手順

## 1. 対象

```text
GPU campaign:
runs/gpu-24h-campaign/20260731-012917

Stage 2:
runs/stage2-expanded-20260731-080740
```

## 2. 基本原則

- 単一GPUでキャンペーンとStage 2を同時実行しない
- PIDだけでなくコマンドラインと対象パスを照合する
- 親終了後も子プロセス残存を確認する
- 終了コード0だけで成功としない
- 実験成果物をGitへ登録しない
- 実行ディレクトリを削除せず監査証跡として保持する

## 3. 現在のプロセス確認

```bash
pgrep -af \
  'start_after_campaign.sh|run_stage2.sh|gpu_24h_campaign.py|loto experiment research' \
  || true
```

GPU確認:

```bash
nvidia-smi \
  --query-gpu=timestamp,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
  --format=csv
```

## 4. キャンペーン進捗確認

```bash
LATEST="/mnt/e/env/ts/loto_forecast_platform/runs/gpu-24h-campaign/20260731-012917"

uv run python - "$LATEST/state.json" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

state = json.loads(
    Path(sys.argv[1]).read_text(encoding="utf-8")
)

counts = Counter(
    str(row.get("status", "UNKNOWN")).upper()
    for row in state.get("trials", [])
)

total = len(state.get("trials", []))
finished = sum(
    counts.get(status, 0)
    for status in ("SUCCEEDED", "FAILED", "TIMEOUT")
)

print("total:", total)
print("succeeded:", counts.get("SUCCEEDED", 0))
print("failed:", counts.get("FAILED", 0))
print("timeout:", counts.get("TIMEOUT", 0))
print("active:", counts.get("ACTIVE", 0))
print("pending:", counts.get("PENDING", 0))
print("progress:", f"{finished / max(total, 1) * 100:.2f}%")
print("deadline:", state.get("deadline_at"))
PY
```

## 5. Stage 2待機確認

```bash
STAGE2_ROOT="/mnt/e/env/ts/loto_forecast_platform/runs/stage2-expanded-20260731-080740"

pgrep -af "$STAGE2_ROOT/start_after_campaign.sh" || true

pgrep -af 'loto experiment research' \
  | grep -F "$STAGE2_ROOT/configs/" \
  && echo "STAGE2_RUNNING=YES" \
  || echo "STAGE2_RUNNING=NO"
```

## 6. Stage 2開始条件

以下をすべて満たすこと。

- 対象キャンペーンパスを含む`gpu_24h_campaign.py`が存在しない
- キャンペーン側の`loto experiment research`が存在しない
- Stage 2の`run_stage2.sh`が存在しない
- Stage 2設定が12件存在
- CV算術検証がPASS
- 設定スキーマ検証がPASS
- GPU上に別学習プロセスが存在しない

## 7. Stage 2成果物

正式成功:

```text
SUCCEEDED
```

条件:

- return code 0
- `research_summary.json`
- `position_mae`
- `position_mse`
- `mean_within_1`

指標不足:

```text
PARTIAL_NO_METRICS
```

タイムアウト:

```text
TIMEOUT
```

その他:

```text
FAILED
```

## 8. 安全な停止

待機プロセスだけ停止:

```bash
pkill -TERM -f \
  'stage2-expanded-20260731-080740/start_after_campaign.sh' \
  || true
```

Stage 2本体だけ停止:

```bash
pkill -TERM -f \
  'stage2-expanded-20260731-080740/configs/' \
  || true
```

対象キャンペーンを停止しないよう、必ずパスを限定する。

## 9. ログ確認

```bash
STAGE2_ROOT="/mnt/e/env/ts/loto_forecast_platform/runs/stage2-expanded-20260731-080740"

find "$STAGE2_ROOT/logs" \
  -maxdepth 1 \
  -type f \
  -name '*.log' \
  -print \
  -exec tail -n 80 {} \;
```

実行結果:

```bash
if [ -f "$STAGE2_ROOT/stage2-execution-results.csv" ]; then
  column -s, -t "$STAGE2_ROOT/stage2-execution-results.csv"
else
  echo "Stage 2は未開始"
fi
```

## 10. Git管理方針

登録する:

- `src/`
- `tests/`
- `scripts/`
- 正式な設定テンプレート
- `docs/`
- `.gitignore`

登録しない:

- `runs/`
- `logs/`
- checkpoint
- 一時設定
- モデル本体
- 大規模CSV/Parquet
- PIDファイル
- キャッシュ
