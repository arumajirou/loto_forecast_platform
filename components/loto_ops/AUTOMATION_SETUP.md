# Loto Ops 自動運用セットアップ

## 短いディレクトリ名

推奨配置先は次です。

```text
/mnt/e/env/ts/loto_ops
```

この配布ZIPは `loto_ops/` をルートとして展開されます。

## OSS UI

StreamlitベースのローカルWeb UIを使用します。

- URL: `http://127.0.0.1:8520`
- Overview: DB接続と主要テーブル件数
- Data Browser: テーブル、列、データプレビュー
- Quality: 品質プロファイルと問題
- Artifacts: レポート、Parquet、ZIP
- Scheduler: 実行状況、進捗、手動実行

## 一括セットアップ

```bash
cd /mnt/e/env/ts/loto_ops
bash install_automation.sh 06:30 8520
```

対話形式で次を入力します。

- PostgreSQLパスワード
- Gmailアドレス
- Gmailアプリパスワード
- 通知先Gmailアドレス
- Slack Incoming Webhook URL

秘密情報は `~/.config/loto-ops/runtime.env` に600権限で保存されます。
PostgreSQL CLI用に `~/.pgpass` も600権限で作成されます。

## 自動実行

- PCログイン時: Streamlit UIを起動
- PCログイン時: パイプラインを1回実行
- 月〜金06:30: パイプラインを実行
- 同じ日に成功済みの場合: 重複実行をスキップ
- 成功・失敗: GmailとSlackへサマリーを通知

## 状態確認

```bash
systemctl --user status loto-ops-ui.service --no-pager
systemctl --user status loto-ops-startup.service --no-pager
systemctl --user status loto-ops-weekday.timer --no-pager
systemctl --user list-timers loto-ops-weekday.timer --all --no-pager
./run_loto_ops.sh schedule-status
```

## 手動通知テスト

```bash
./scripts/test_notifications.sh
```

## 手動パイプライン実行

```bash
./scripts/run_scheduled_pipeline.sh manual
```

## 無効化

```bash
systemctl --user disable --now loto-ops-ui.service
systemctl --user disable loto-ops-startup.service
systemctl --user disable --now loto-ops-weekday.timer
rm -f ~/.config/autostart/loto-ops-open-ui.desktop
systemctl --user daemon-reload
```
