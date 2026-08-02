# 17. 通知設計: Gmail / Slack

## 目的

`scripts/run_scheduled_pipeline.sh` の実行終了時に、実行概要・進捗・重要DB件数・成果物ZIP・ログパスを通知する。

対象チャネル:

- Gmail / SMTP
- Slack Incoming Webhook

## 基本方針

- 認証情報はコードへ埋め込まない。
- `configs/notify.env` に秘密情報を置く。
- `configs/notify.env.example` を雛形として提供する。
- 通知送信失敗でパイプライン本体は失敗扱いにしない。
- 成功時・失敗時の両方で通知できる。

## 設定ファイル作成

```bash
cd /mnt/e/env/ts/loto_ops
cp configs/notify.env.example configs/notify.env
chmod 600 configs/notify.env
nano configs/notify.env
```

最小設定例:

```bash
LOTO_NOTIFY_ENABLED=1
LOTO_NOTIFY_ON_SUCCESS=1
LOTO_NOTIFY_ON_FAILURE=1

LOTO_NOTIFY_EMAIL_ENABLED=1
LOTO_NOTIFY_EMAIL_TO=you@example.com
LOTO_NOTIFY_EMAIL_FROM=loto-ops@example.com
LOTO_NOTIFY_SMTP_HOST=smtp.example.com
LOTO_NOTIFY_SMTP_PORT=587
LOTO_NOTIFY_SMTP_STARTTLS=1
LOTO_NOTIFY_SMTP_USER=your-smtp-user
LOTO_NOTIFY_SMTP_PASSWORD=CHANGE_ME

LOTO_NOTIFY_SLACK_ENABLED=1
LOTO_NOTIFY_SLACK_WEBHOOK_URL=
```

## テスト送信

```bash
cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh
./scripts/test_notify.sh
```

または直接:

```bash
loto-ops notify-test --message "Loto Ops notification test"
```

## 実行結果サマリーを手動送信

```bash
loto-ops notify-run-summary
```

直近実行ログを明示する場合:

```bash
loto-ops notify-run-summary \
  --status success \
  --reason manual_check \
  --log-file /mnt/e/env/ts/loto_ops/logs/scheduler/manual_xxx.log
```

## 定期実行時の動作

`run_scheduled_pipeline.sh` は終了時に `notify-run-summary` を呼び出す。

- 正常終了: `status=success`
- 失敗終了: `status=failed`
- `LOTO_NOTIFY_ON_SUCCESS=0`: 成功通知を抑制
- `LOTO_NOTIFY_ON_FAILURE=0`: 失敗通知を抑制
- `LOTO_NOTIFY_ENABLED=0`: 全通知を停止

## 通知に含める内容

- status
- reason
- started_at / finished_at
- progress percent
- current_step
- 重要テーブル件数
  - `dataset.loto_y_ts`
  - `dataset.loto_hist_feat`
  - `exog.loto_y_ts_exog`
  - `dataset.loto_y_ts_unified`
- 成果物ZIPパス
- scheduler log path
- progress.json path
- step一覧
- 直近ログ末尾

## 注意

Gmailでは通常のGoogleアカウントパスワードではなく、SMTP用のアプリパスワードを使う。SlackはIncoming Webhook URLを `LOTO_NOTIFY_SLACK_WEBHOOK_URL` に設定する。
