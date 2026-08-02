# 仮想環境の有効化手順

## 基本

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
source ./activate_env.sh
```

`source` を使う理由は、シェルスクリプトを普通に実行しても親シェルの `PATH` や `VIRTUAL_ENV` を変更できないためです。

## セットアップ込み

```bash
cd /mnt/e/env/ts/loto_ops
source scripts/setup_and_activate.sh
```

## 新しい有効化済みシェル

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/enter_env.sh
```

## 確認

```bash
which python
python -V
which loto-ops
loto-ops --help
```

## 有効化時に設定される主な環境変数

```text
VIRTUAL_ENV
PATH
PYTHONPATH
LOTO_OPS_HOME
UV_LINK_MODE=copy
POLARS_MAX_THREADS=24
RAYON_NUM_THREADS=24
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_MAX_THREADS=16
```

## 無効化

```bash
deactivate
```
