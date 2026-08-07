# Prompt — Database Migration Foundation v1

```text
@GitHub

対象リポジトリ:
https://github.com/arumajirou/loto_forecast_platform

あなたは時系列予測プラットフォームのOperational Resilience担当リードエンジニアです。

## 絶対条件

- default branchと最新main HEADを実行直前に再取得する。
- 事前情報のmain SHA `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0` を固定値として信用しない。
- 同一目的のopen/closed PR、Issue、branch、package pathを再検索する。
- PR #120〜#134、および実行時点で追加されたcross-cutting PRを再監査する。
- 重複または意味的所有権衝突があれば実装せず、根拠を報告して停止する。
- 最新mainから独立branchを作成し、Draft PRのみ作成する。
- mainへの直接変更、force push、rebase、reset、history rewrite、Ready変更、merge、
  auto-merge、branch削除を禁止する。
- dirty worktreeを変更しない。isolated worktreeまたはclean cloneを使用する。
- Holdout、Prospective actual、production Registry/Promotionを開かない。
- PR #121 `src/loto/configuration/**`、PR #123 `src/loto/runtime_certification/**`、
  PR #124 `src/loto/data_access_ledger/**`、PR #125 `src/loto/trusted_evidence/**`、
  PR #127 API readiness、PR #132 Feature Availability、PR #133 GitHub audit、
  PR #134 Research Source Registryを再実装しない。
- Pythonはuv、src、tests、Pydantic v2、Ruff、mypy、pytest、pytest-covを使用する。
- 変更中はfocused tests、compileall、Ruff、mypy、smokeを先に行う。
- 重いfull pytestは実装とfocused validationが安定した最後に一度だけ実行する。
- GitHub Actionsがstepsなし/logなしで失敗する場合は
  `CI_BLOCKED_RUNNER_START`として記録し、code failureと断定せず、blind rerunしない。
- 実行していない検証をPASSと書かない。
- 成果物にはREADME、REQUIREMENTS、SPECIFICATIONまたはFUNCTIONAL_SPECIFICATION、
  ARCHITECTURE、DATA_CONTRACT、TEST_PLAN、VERIFICATION_REPORT、CHANGELOG、HANDOFF、
  RUNBOOK、ARTIFACT_MANIFEST、SHA256SUMSを含める。
- すべての状態、証拠、非主張をmachine-readableに保存する。

TARGET_PR=Database Migration Foundation v1
BRANCH=feat/database-migration-foundation-v1
PR_MODE=Draft

## 開始条件

PR #120、#133、その他root pyproject.toml/uv.lock変更PRとのconflictを再監査する。
同時編集が危険なら実装を停止し、推奨base/順序を報告する。

mainのobserved pyprojectではSQLAlchemy/psycopgがpostgres extraにあり、
Alembicは未宣言だった。実行時点で必ず再確認する。

## 目的

Alembicを用いた明示的migration control planeを導入する。
application import、API startup、worker startupから自動upgradeしてはいけない。
既存legacy schemaを未検証のままstampしてはいけない。

## 許可scope

- alembic.ini
- migrations/**
- src/loto/persistence_migrations/**
- tests/persistence_migrations/**
- docs/persistence_migrations/**
- scripts/manage_database_migrations.py
- pyproject.toml
- uv.lock

## 必須機能

- check / current / heads / history / plan / offline-sql / upgrade / downgrade
- strict MigrationRequest / MigrationEvidence / MigrationVerificationReport
- DSN redaction
- migration script SHA-256
- offline SQL SHA-256
- no-opまたは新規ops領域だけのnon-destructive baseline
- legacy schema inventory status=UNADOPTED
- divergent heads拒否
- missing migration検出
- target applyにはexplicit tokenとreview evidence
- backup confirmation interface（実backupは別PR）
- atomic evidence output

## Dependency

Alembic version/license/compatibilityを公式情報とtarget Pythonで確認する。
追加はbounded pinで行い、uv.lockを一度だけ再生成・検証する。
不要なdependency更新を混入させない。

## 必須tests

empty SQLite upgrade/downgrade/upgrade、offline SQL、single head、duplicate revision、
import-no-migration、unknown legacy DB not stamped、DSN redaction、wrong token、
script tamper、failed migration evidence。
Docker利用可能ならephemeral PostgreSQLを追加するが、未実行時はBLOCKED。

## 非主張

existing production schema adopted=false
production migrated=false
backup verified=false
PostgreSQL verified=false unless actually executed
```
