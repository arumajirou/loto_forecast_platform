# PPL-01 Native インストール・動作確認

## 1. Linux/Kubuntu

```bash
cd "$HOME/Downloads" || exit 1

sha256sum -c \
  loto_forecast_platform_ppl01_native_full.zip.sha256

mkdir -p /mnt/e/env/ts
unzip -q \
  loto_forecast_platform_ppl01_native_full.zip \
  -d /mnt/e/env/ts

cd /mnt/e/env/ts/loto_forecast_platform_ppl01_native_full || exit 1

chmod +x \
  scripts/probabilistic/install_linux.sh \
  scripts/probabilistic/run_native_smoke_linux.sh \
  tools/verify_native_ppl_implementation.py
```

### 1.1 ネイティブruntime一括導入

```bash
PPL_INSTALL_MODE=native \
  ./scripts/probabilistic/install_linux.sh "$PWD"
```

このモードはPyMC、PyMC-BART、JAX、NumPyro、BlackJAX、Pyro、ArviZを
1回のresolver transactionで導入し、必要backendのimportと72件の主経路を厳格検査する。
依存導入に失敗した場合はPASSを出さない。

### 1.2 静的検証

```bash
uv run python tools/verify_native_ppl_implementation.py \
  --root "$PWD"
```

期待値:

```text
status = PASS
models = 72
silent_substitutions = 0
```

### 1.3 runtime必須検証

```bash
uv run python tools/verify_native_ppl_implementation.py \
  --root "$PWD" \
  --require-runtime
```

必要backend:

- builtin
- arviz
- pymc
- pymc_bart
- numpyro
- pyro

### 1.4 72モデルnative smoke

```bash
./scripts/probabilistic/run_native_smoke_linux.sh "$PWD"
```

期待値:

```text
PPL01_NATIVE_PLAN=PASS
PPL01_NATIVE_SMOKE=PASS
PASS = 72
```

### 1.5 標準実行

```bash
uv run loto3 probabilistic run \
  --config configs/probabilistic/native_standard.yaml \
  | tee artifacts/ppl01-native-standard.json
```

### 1.6 フル実行

```bash
uv run loto3 probabilistic run \
  --config configs/probabilistic/native_full.yaml \
  | tee artifacts/ppl01-native-full.json
```

`native_full.yaml`は4 chains、1,000 warmup、1,000 draws、SVI 30,000 steps、
5 seeds、5 foldsを含むため高負荷である。先にsmokeとstandardを通すこと。

## 2. 実Numbers3データ

```bash
DATA_PATH="/mnt/e/env/ts/loto_forecast_platform/runs/data-acquisition-all/numbers3/normalized/numbers3.csv"
test -f "$DATA_PATH"

uv run python - "$DATA_PATH" <<'PY'
from pathlib import Path
import sys
import yaml

source = Path("configs/probabilistic/native_standard.yaml")
target = Path("configs/probabilistic/native_numbers3_real.yaml")
config = yaml.safe_load(source.read_text(encoding="utf-8"))
config.update(
    {
        "run_id": "numbers3-native-real",
        "games": ["numbers3"],
        "inputs": {"numbers3": str(Path(sys.argv[1]).resolve())},
        "test_size": 40,
        "min_train_size": 500,
        "seeds": [42],
    }
)
target.write_text(
    yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
    encoding="utf-8",
)
print(target)
PY

uv run loto3 probabilistic plan \
  --config configs/probabilistic/native_numbers3_real.yaml \
  > artifacts/ppl01-native-numbers3-plan.json

uv run loto3 probabilistic run \
  --config configs/probabilistic/native_numbers3_real.yaml \
  | tee artifacts/ppl01-native-numbers3-run.json
```

Numbers3非対応モデルが含まれる場合はBLOCKEDになる。終了コード0へ統一する場合は、
planの`allowed=true`モデルだけを`models`へ指定する。

## 3. Windows PowerShell

```powershell
$Zip = "$HOME\Downloads\loto_forecast_platform_ppl01_native_full.zip"
$Parent = "C:\Users\bp00425\env\ts"
$Root = Join-Path $Parent "loto_forecast_platform_ppl01_native_full"

New-Item -ItemType Directory -Force -Path $Parent | Out-Null
Expand-Archive -LiteralPath $Zip -DestinationPath $Parent -Force
Set-Location $Root

powershell.exe `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File ".\scripts\probabilistic\install_windows.ps1" `
  -Root $Root `
  -Mode native
```

72モデルsmoke:

```powershell
powershell.exe `
  -NoProfile `
  -ExecutionPolicy Bypass `
  -File ".\scripts\probabilistic\run_native_smoke_windows.ps1" `
  -Root $Root
```

自動実行時のみ`-NoPause`を追加する。

## 4. 状態確認

```bash
uv run loto3 probabilistic native-coverage
uv run loto3 probabilistic backends
uv run loto3 probabilistic plan \
  --config configs/probabilistic/native_smoke.yaml
```

`native-coverage`はコード実装の網羅性、`backends`は現在環境のimport可否、
`plan`は両者とゲーム互換性を結合した実行可否を表す。
