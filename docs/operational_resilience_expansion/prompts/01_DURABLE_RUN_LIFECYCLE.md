# Prompt — Durable Run Lifecycle Contract v1

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

TARGET_PR=Durable Run Lifecycle Contract v1
BRANCH=feat/durable-run-lifecycle-contract-v1
PR_MODE=Draft

## 目的

長時間Runの状態、idempotency、lease、heartbeat、fencing token、resume、cancel、
retry分類、append-only event chainをprovider-neutralに実装する。
今回はfoundationのみで、DB、Temporal、Dagster、API、既存pipeline統合は行わない。

## 許可scope

- src/loto/run_lifecycle/**
- tests/run_lifecycle/**
- docs/run_lifecycle/**
- configs/run_lifecycle/**

root pyproject.toml、uv.lock、workflow、既存orchestration、Prediction Lock、
Runtime Certification、Data Access Ledger、Registry、Promotionは変更しない。

## 必須contract

- RunPhase
- RunStatus
- RunCommand
- RunEvent
- RunLease
- RunAggregate
- IdempotencyRecord
- TransitionDecision
- LifecycleValidationReport

Pydantic v2:
ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)
allow_inf_nan=false
UTC必須
lowercase SHA-256必須

## 必須ロジック

- phaseとstatusを分離
- machine-readable transition matrix
- gap-free sequence
- previous-event hash chain
- deterministic semantic idempotency key
- duplicate commandは再実行せず同じresultを返す
- lease acquisition/renewal/expiry
- monotonically increasing fencing token
- stale tokenのmutation拒否
- explicit cancellation
- terminal stateのimmutability
- injected clock
- in-memory repository
- atomic service semantics
- evidence referenceはopaque ID/hashとして扱い、他PRのschemaをコピーしない

## 必須negative tests

unknown field、型coercion、invalid transition、event reorder、gap、duplicate、
hash tamper、expired lease renewal、stale fencing token、duplicate command、
cancel後の続行、terminal state変更、idempotency collision、naive datetime、
NaN/Infinity。

Hypothesis state-machine testを追加する。

## 明示的非主張

database durability=false
process restart durability=false
Temporal/Dagster integration=false
Prediction Lock integration=false
real workflow migration=false
Holdout=false
Prospective=false

focused testsとpure in-memory smokeがPASSしても、real durable executionとは書かない。
```
