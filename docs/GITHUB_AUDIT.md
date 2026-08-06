# GitHub Repository Audit

`loto-github-audit`は、GitHubリポジトリの状態を読み取り専用で収集し、
JSON・CSV・Markdown・HTML・SHA-256・ZIPとして固定する運用監査機能です。

既定対象は`arumajirou/loto_forecast_platform`です。

## 取得範囲

- Repository metadata、既定branch HEAD、Commit Status、Check Runs
- Issues、Pull Requests、branch、commit、tag、release、contributor
- Actions workflows、runs、jobs、runner、cache、artifact、permissions
- Rulesets、branch protection、environments、collaborators
- Dependabot、Code scanning、Secret scanning、Security advisories
- Dependency graph SBOM、Dependabot configuration
- Secret・Variable・Webhook・Deploy keyの安全なメタデータ
- 重複Issue候補とPR stack graph

`--deep`では、開放Issueのコメント・イベント、開放PRのレビュー・review thread・
変更ファイル・check・workflow、指定件数のActions jobを追加取得します。

GitHubへ書き込みません。権限不足や機能未設定は、空配列として成功扱いせず、
`BLOCKED`、`NOT_AVAILABLE`、`RATE_LIMITED`、`FAILED`として記録します。

Secret値、Actions Variable値、Webhook callback URL、Deploy key materialは出力しません。

## 必要条件

- Python 3.11以上
- `uv`（推奨）またはPython
- GitHub CLI `gh`
- 対象repositoryを読める`gh`認証

認証確認:

```bash
gh auth status --hostname github.com
```

未認証の場合:

```bash
gh auth login --hostname github.com
```

Security APIまで取得する認証方式では、必要に応じてscopeを追加します。

```bash
gh auth refresh --hostname github.com --scopes repo,read:org,workflow,security_events
```

## Linux / WSL

### CLIを直接実行

```bash
cd /mnt/e/env/ts/loto_forecast_platform

uv run loto-github-audit \
  --repo arumajirou/loto_forecast_platform \
  --output-root artifacts/github-audit \
  --deep
```

### launcherを使用

```bash
cd /mnt/e/env/ts/loto_forecast_platform

bash scripts/run_github_audit.sh
```

追加引数はそのままCLIへ渡せます。

```bash
bash scripts/run_github_audit.sh \
  --max-action-runs 1000 \
  --max-run-jobs 200 \
  --max-pr-details 300
```

環境変数でも既定値を変更できます。

```bash
export GITHUB_AUDIT_REPO="arumajirou/loto_forecast_platform"
export GITHUB_AUDIT_OUTPUT_ROOT="/mnt/e/env/logs/github-audit"
export GITHUB_AUDIT_DEEP=1
bash scripts/run_github_audit.sh
```

## Windows PowerShell

```powershell
Set-Location E:\env\ts\loto_forecast_platform
Set-ExecutionPolicy -Scope Process Bypass

.\scripts\run_github_audit.ps1 `
  -Repo "arumajirou/loto_forecast_platform" `
  -OutputRoot "E:\env\logs\github-audit" `
  -Deep
```

終了時のEnter待ちを無効化:

```powershell
.\scripts\run_github_audit.ps1 `
  -Repo "arumajirou/loto_forecast_platform" `
  -Deep `
  -NoPause
```

CLIを直接実行:

```powershell
uv run loto-github-audit `
  --repo arumajirou/loto_forecast_platform `
  --output-root artifacts\github-audit `
  --deep
```

## 軽量実行

`--deep`を付けない場合、一覧・設定・Security・依存関係を中心に取得し、
PR・Issueごとの詳細API呼び出しを省略します。

```bash
uv run loto-github-audit \
  --repo arumajirou/loto_forecast_platform \
  --output-root artifacts/github-audit
```

## 自己テスト

GitHubへ接続せず、分類・秘匿化・CLIの基本処理を検査します。

```bash
uv run loto-github-audit --self-test
```

期待値:

```json
{"status": "PASS", "test": "github_audit_self_test"}
```

## 出力

```text
artifacts/github-audit/
├── arumajirou-loto_forecast_platform-audit-YYYYMMDDTHHMMSSZ/
│   ├── REPORT.md
│   ├── REPORT.html
│   ├── SUMMARY.json
│   ├── MANUAL_CHECKS.md
│   ├── ARTIFACT_MANIFEST.json
│   ├── SHA256SUMS
│   ├── status.txt
│   ├── exit_code.txt
│   ├── raw/
│   ├── tables/
│   └── logs/
├── arumajirou-loto_forecast_platform-audit-YYYYMMDDTHHMMSSZ.zip
└── arumajirou-loto_forecast_platform-audit-YYYYMMDDTHHMMSSZ.zip.sha256
```

主なCSV:

- `issues.csv`
- `pull_requests.csv`
- `workflows.csv`
- `workflow_runs.csv`
- `action_run_jobs.csv`
- `security_alerts.csv`
- `endpoint_status.csv`
- `possible_duplicate_issues.csv`

`pr_stack.dot`はGraphvizで可視化できます。

```bash
dot -Tpng tables/pr_stack.dot -o pr_stack.png
```

## 終了コード

- `0`: 必須endpointを取得し、監査成果物を生成
- `1`: CLI、認証、ファイル生成などの実行失敗
- `2`: 必須endpointの一部が取得不能で`PARTIALLY_VERIFIED`
- `130`: ユーザー割り込み

Securityや管理設定の一部だけが`BLOCKED`でも、必須endpointが取得できれば終了コードは`0`です。
詳細は`tables/endpoint_status.csv`と`MANUAL_CHECKS.md`で確認します。
