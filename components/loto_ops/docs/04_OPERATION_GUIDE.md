# 運用手順書

## 通常実行

```bash
uv run loto-ops run-all --with-analysis --with-zip
```

## exog必須で実行

```bash
uv run loto-ops run-all --with-exog --with-analysis --with-zip
```

## Web起動

```bash
uv run loto-ops webapp --port 8520
```

## ZIP作成

```bash
uv run loto-ops package --mode light
uv run loto-ops package --mode full
```

## 日次実行設定

```bash
uv run loto-ops schedule-install --time 06:30
systemctl --user enable --now loto-ops-daily.timer
```
