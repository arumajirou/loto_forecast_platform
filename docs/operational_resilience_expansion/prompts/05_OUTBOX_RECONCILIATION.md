# Prompt — Persistence Outbox and Reconciliation v1

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

TARGET_PR=Persistence Outbox and Reconciliation v1
BRANCH=feat/persistence-outbox-reconciliation-v1
PR_MODE=Draft

## Dependency

Database Migration Foundation v1がreview可能な状態で、同一integration checkoutに存在すること。
Durable Run Lifecycle Contract v1のID、lease、fencing semanticsを再利用する。
copyは禁止。利用できなければ実装を停止するか、Protocol adapterだけに縮小する。

## 目的

PostgreSQL authoritative stateと同一transactionでoutboxを作成し、
MLflow、Parquet、artifact storage等への部分成功をretry/reconcileする。
「exactly-once delivery」と主張せず「at-least-once delivery + exactly-once effect」を設計する。

## 許可scope

- src/loto/persistence_outbox/**
- tests/persistence_outbox/**
- docs/persistence_outbox/**
- configs/persistence_outbox/**
- scripts/run_outbox_dispatcher.py
- scripts/run_reconciliation.py
- migrations/versions/<new revisions>

既存MLflow/Registry/Promotion実装の直接rewireは別PR。

## 必須table/contract

- outbox_message
- delivery_attempt
- destination_receipt
- reconciliation_run
- idempotency_record
- Destination Protocol
- ReceiptVerifier Protocol

## 必須ロジック

- state update + outbox insert same transaction
- unique semantic key
- claim lease + fencing
- PostgreSQL SKIP LOCKED adapter
- bounded retry/backoff
- poison state
- destination read-back verification
- required destination inventory
- missing/orphan/hash-conflict/duplicate receipt detection
- conflictはmanual review、automatic overwrite禁止
- failed evidence保持
- reconciliation idempotent

## 必須tests

commit/rollback atomicity、duplicate key、parallel claim、stale worker、partial delivery、
retry、poison、duplicate receipt、missing destination、orphan、hash conflict、
reconciliation rerun、process kill after commit simulation。
SQLite PASSをPostgreSQL concurrency証明として扱わない。

## 非主張

live MLflow=false
live artifact store=false
production Postgres=false unless executed
all existing workflows integrated=false
```
