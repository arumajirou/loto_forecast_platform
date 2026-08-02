# Loto Ops v3 changes

- 配置名を `loto_ops` に短縮
- Streamlit OSS UIをsystemd user serviceで自動起動
- ブラウザを `http://127.0.0.1:8520` で自動表示
- PC起動時にパイプラインを実行
- 月〜金06:30に1日1回実行
- 同日成功済みの場合は重複実行を抑止
- Gmail SMTPとSlack Incoming Webhookへ成功・失敗を通知
- DB/Gmail/Slack秘密情報を `~/.config/loto-ops/runtime.env` に分離
- `.pgpass`を作成してpsql認証を自動化
- 旧 `/mnt/e/env/fc/loto_ops_pipeline` などの固定パスを除去
- 既存のPostgreSQL、SQLite、外部データディレクトリを継続利用
