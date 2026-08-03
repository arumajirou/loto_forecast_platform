# PPL-01 インストール・動作確認

## 1. Linux / Kubuntu

### 1.1 展開

```bash
mkdir -p /mnt/e/env/ts
cd /mnt/e/env/ts

unzip -q \
  ~/Downloads/loto_forecast_platform_ppl01_implemented.zip

cd loto_forecast_platform_ppl01_implemented
```

### 1.2 参照実装をインストール

```bash
chmod +x \
  scripts/probabilistic/install_linux.sh \
  scripts/probabilistic/run_smoke_linux.sh \
  tools/verify_probabilistic_implementation.sh

PPL_INSTALL_MODE=reference \
  ./scripts/probabilistic/install_linux.sh "$PWD"
```

既存lockを使用してプロジェクト環境を作成し、カタログ、バックエンド、設定契約を検査する。

### 1.3 静的検証

```bash
./tools/verify_probabilistic_implementation.sh
```

期待値:

```text
PPL01_STATIC_VERIFICATION=PASS
```

### 1.4 72モデル一括スモーク

```bash
./scripts/probabilistic/run_smoke_linux.sh "$PWD" \
  | tee artifacts/ppl01-smoke-command.log
```

期待される主要値:

```text
models_planned = 72
trials_total   = 72
PASS           = 72
```

### 1.5 標準rolling評価

```bash
uv run loto3 probabilistic run \
  --config configs/probabilistic/standard.yaml \
  | tee artifacts/ppl01-standard-command.json
```

### 1.6 バックエンド状態

```bash
uv run loto3 probabilistic backends
```

`available=true`だけでなく、`implemented`と`detail`を確認する。パッケージが存在してもimportに失敗する場合はAVAILABLEにならない。

## 2. 実データで実行

Numbers3正規化CSVを使用する例:

```bash
cd /mnt/e/env/ts/loto_forecast_platform_ppl01_implemented

uv run python - <<'PY'
from pathlib import Path
import yaml

source = Path("configs/probabilistic/standard.yaml")
target = Path("configs/probabilistic/local_numbers3.yaml")
config = yaml.safe_load(source.read_text(encoding="utf-8"))
config.update({
    "run_id": "numbers3-ppl-local",
    "games": ["numbers3"],
    "inputs": {
        "numbers3": (
            "runs/data-acquisition-all/numbers3/"
            "normalized/numbers3.csv"
        )
    },
    "test_size": 40,
    "min_train_size": 500,
    "posterior_draws": 512,
    "seeds": [42],
})
target.write_text(
    yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
    encoding="utf-8",
)
print(target)
PY

uv run loto3 probabilistic validate-config \
  --config configs/probabilistic/local_numbers3.yaml

uv run loto3 probabilistic plan \
  --config configs/probabilistic/local_numbers3.yaml \
  > artifacts/ppl01-local-plan.json

uv run loto3 probabilistic run \
  --config configs/probabilistic/local_numbers3.yaml \
  | tee artifacts/ppl01-local-run.json
```

結果ディレクトリは出力JSONの`run_dir`に表示される。

```bash
RUN_DIR="runs/probabilistic/numbers3-ppl-local"

uv run loto3 probabilistic status \
  --run-dir "$RUN_DIR"

uv run loto3 probabilistic diagnose \
  --run-dir "$RUN_DIR"

uv run loto3 probabilistic compare \
  --run-dir "$RUN_DIR"

find "$RUN_DIR" -maxdepth 3 -type f | sort | less
```

## 3. ネイティブPPLライブラリの導入試行

### 3.1 PyMC

```bash
PPL_INSTALL_MODE=pymc \
  ./scripts/probabilistic/install_linux.sh "$PWD"

uv run loto3 probabilistic backends
```

### 3.2 JAX / NumPyro / BlackJAX

```bash
PPL_INSTALL_MODE=jax \
  ./scripts/probabilistic/install_linux.sh "$PWD"

uv run loto3 probabilistic backends
```

### 3.3 Pyro

```bash
PPL_INSTALL_MODE=pyro \
  ./scripts/probabilistic/install_linux.sh "$PWD"
```

### 3.4 CmdStanPy

```bash
PPL_INSTALL_MODE=stan \
  ./scripts/probabilistic/install_linux.sh "$PWD"
```

### 3.5 一括試行

```bash
PPL_INSTALL_MODE=all \
  ./scripts/probabilistic/install_linux.sh "$PWD"
```

一括モードは各任意バックエンドを試行し、失敗したものをログへ残して次へ進む。導入成功は`probabilistic backends`の実import結果で判定する。

## 4. オフライン・既存環境フォールバック

既にnumpy、pandas、pydantic、PyYAML、scipy、scikit-learnが使用でき、`uv sync`だけがネットワーク理由で失敗する場合:

```bash
cd /mnt/e/env/ts/loto_forecast_platform_ppl01_implemented

export PYTHONPATH="$PWD/src:$PWD"

python -m loto.cli_v3 probabilistic catalog-list
python -m loto.cli_v3 probabilistic plan \
  --config configs/probabilistic/smoke.yaml
python -m loto.cli_v3 probabilistic smoke \
  --config configs/probabilistic/smoke.yaml
```

これは開発用フォールバックであり、通常運用ではlockされた`uv`環境を使用する。

## 5. Windows PowerShell

```powershell
$Zip = "$HOME\Downloads\loto_forecast_platform_ppl01_implemented.zip"
$Parent = "C:\Users\bp00425\env\ts"
$Root = Join-Path $Parent "loto_forecast_platform_ppl01_implemented"

New-Item -ItemType Directory -Force -Path $Parent | Out-Null
Expand-Archive -LiteralPath $Zip -DestinationPath $Parent -Force
Set-Location $Root

powershell.exe `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File ".\scripts\probabilistic\install_windows.ps1" `
  -Root $Root `
  -Mode reference
```

72モデルスモーク:

```powershell
powershell.exe `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File ".\scripts\probabilistic\run_smoke_windows.ps1" `
  -Root $Root
```

ウィンドウを自動で閉じたくない場合、既定のまま実行する。自動化時だけ`-NoPause`を付ける。

## 6. テスト

PPL対象:

```bash
PYTHONPATH=src:. \
  uv run pytest -q tests/probabilistic
```

既存の主要契約を含む対象回帰:

```bash
PYTHONPATH=src:. \
  uv run pytest -q \
    tests/test_cli_v3.py \
    tests/test_catalog_full.py \
    tests/test_protocol_hash.py \
    tests/test_models.py \
    tests/probabilistic
```

## 7. 成果物確認

各trialには最低限次が保存される。

```text
model_spec.json
protocol.json
execution_fingerprint.json
posterior_reference.json
posterior_summary.csv
rolling_predictions.csv
next_prediction.json
diagnostics.json
lifecycle_result.json
SHA256SUMS.json
```

run全体には次が保存される。

```text
run_config.yaml
plan.json
environment.json
catalog_counts.json
results.json
results.csv
comparison/leaderboards.json
report/summary.json
SHA256SUMS.json
```
