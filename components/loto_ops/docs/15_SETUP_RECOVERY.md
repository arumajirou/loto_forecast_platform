# Setup Recovery / Network Timeout Safe Install

v3.9 では、CLIに不要なWeb依存（Streamlit/Plotly）を任意extraへ分離しました。
これにより、uvicornなどのダウンロード失敗で `loto-ops` CLI 全体が使えなくなる問題を避けます。

## CLI最小セットアップ

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
source ./activate_env.sh
loto-ops --help
```

## Webアプリを使う場合だけ

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_web.sh
source ./activate_env.sh
loto-ops webapp --port 8520 --auto-port
```

## `loto-ops: コマンドが見つかりません` の復旧

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
source ./activate_env.sh
command -v loto-ops
python -m loto_ops.cli --help
```
