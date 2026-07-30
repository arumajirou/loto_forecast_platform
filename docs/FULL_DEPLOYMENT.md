# Full Deployment

## 1. Secrets

`.env.full.example`を複製し、PostgreSQL、Grafana、HMAC封印鍵、API Tokenを設定する。`.env`はGitへ登録しない。

## 2. 起動

```bash
cd docker
docker compose --env-file ../.env -f compose.full.yaml up -d --build
```

## 3. Health確認

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:5050/health
curl -fsS http://127.0.0.1:9090/-/healthy
```

## 4. 認証確認

```bash
curl -H 'Authorization: Bearer viewer-token' http://127.0.0.1:8080/registry/runs
```

## 5. 二段階承認

Operatorが申請し、異なるApproverが判断する。同一ユーザーによる自己承認は台帳層で拒否される。

## 6. ロールバック

直前の署名済みRelease Bundleを指定し、Bundle検証に成功した場合のみ切り戻す。封印済みForecastは上書きせず取消レコードを追記する。
