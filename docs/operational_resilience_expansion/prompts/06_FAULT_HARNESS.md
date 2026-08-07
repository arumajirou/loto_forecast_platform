# Prompt — Target-host Integration Fault Harness v1

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

TARGET_PR=Target-host Integration Fault Harness v1
BRANCH=test/target-host-fault-harness-v1
PR_MODE=Draft

## 開始条件

Lifecycle、migration、outbox/reconciliationが同一review checkoutで利用可能であること。
Docker/Testcontainers/Toxiproxyのversion、license、target-host互換性を再確認する。
production DSN、production artifact root、Holdout、Prospectiveへ絶対接続しない。

## 目的

real ephemeral PostgreSQLとnetwork fault proxyを使い、process kill、timeout、reset、
duplicate、restart後のresume/reconciliationを検証するtarget-host harnessを実装する。

## 許可scope

- tests/integration/faults/**
- src/loto/testing/faults/** または既存testing packageのbounded path
- scripts/run_fault_harness.py
- scripts/run_fault_harness.sh
- scripts/run_fault_harness.ps1
- docs/fault_harness/**
- configs/fault_harness/**
- 必要なdev/integration extraとuv.lock

production runtime pathは変更しない。

## 必須scenario

F01 duplicate command
F02 stale fencing token
F03 kill after DB commit
F04 destination unavailable
F05 timeout/reset
F06 restart and resume
F07 artifact hash conflict
F08 unhealthy clock blocks lock precondition
F09 sandbox network denial

## 必須成果物

SCENARIO_PLAN.json
HOST_INVENTORY.json
CONTAINER_INVENTORY.json
FAULT_EVENTS.jsonl
APPLICATION_EVENTS.jsonl
RECOVERY_REPORT.json
RECONCILIATION_REPORT.json
VERIFICATION_REPORT.md
ARTIFACT_MANIFEST.json
SHA256SUMS
evidence ZIP + sidecar

## 判定

fault injection successとapplication recovery successを分離する。
全scenarioでno duplicate semantic effect、no stale write、eventual reconciliation、
hash integrityを確認する。
GPU scenarioは別phase、1 jobのみ、CPU/storage PASS後。

## 必須安全策

- ephemeral database name/port
- explicit production deny patterns
- output workspace outside repository
- timeout and cleanup
- container/image digest retention
- secret redaction
- Enterキーで終了するoperator wrapper
- failure時もevidenceを削除しない

## 非主張

production resilience=false
backup/restore certified=false
GitHub CI fault execution=false
GPU fault certified=false unless actually executed
```
