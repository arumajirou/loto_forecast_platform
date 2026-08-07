# Prompt — Clock Health Gate v1

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

TARGET_PR=Clock Health Gate v1
BRANCH=feat/clock-health-gate-v1
PR_MODE=Draft

## 目的

Prediction Lock前にhost clockの運用健全性を判定する共通gateを実装する。
PR #125のTrusted Time/Actual Source schemaを変更・再定義しない。
HEALTHY local clockをtrusted third-party timeへ昇格しない。

## 許可scope

- src/loto/clock_health/**
- tests/clock_health/**
- docs/clock_health/**
- configs/clock_health/**
- scripts/run_clock_health_check.py

既存Prediction Lockへの本接続は別PRとする。

## 必須contract

- ClockObservation
- ClockSourceObservation
- ClockHealthPolicy
- ClockHealthDecision
- ClockContinuityEvidence
- ClockParserEvidence

## 必須判定

HEALTHY / DEGRADED / BLOCKED / UNKNOWN

検査:
- synchronized
- leap status
- stratum
- absolute last offset
- RMS offset
- root delay
- root dispersion
- skew ppm
- online source count
- sample age
- wall-clockとmonotonicのstep検出
- parser identityとraw observation SHA-256

core serviceはsubprocessを直接呼ばず、injected observationで動く。
chronyc adapterはargv固定、shell禁止、timeout、stderr hash、exit codeを記録する。

## Prediction Lock境界

`prediction_lock_allowed=true`はHEALTHYだけ。
ただしこれはoperational preconditionであり、
EXTERNALLY_TIMESTAMPED_VERIFIEDやSIGNATURE_VERIFIEDを生成してはいけない。

## 必須tests

healthy、warning/degraded、unsynchronized、offset block、dispersion block、stale sample、
zero source、malformed chronyc、unknown field、duplicate JSON key、clock step、
raw tamper、policy hash change、local-to-trusted promotion禁止。

## 非主張

real chrony host verification=false
trusted timestamp=false
RFC3161=false
Sigstore=false
existing Prediction Lock modified=false
```
