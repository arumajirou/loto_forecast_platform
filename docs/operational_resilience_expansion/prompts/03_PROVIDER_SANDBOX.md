# Prompt — Untrusted Provider Sandbox Contract v1

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

TARGET_PR=Untrusted Provider Sandbox Contract v1
BRANCH=feat/untrusted-provider-sandbox-contract-v1
PR_MODE=Draft

## 目的

trust_remote_codeや外部provider codeをhostから隔離する共通sandbox contract、
argv builder、environment/mount validator、effective evidence verifierを実装する。
PR #123 Runtime Certification SDKを置換しない。model outputの正当性は扱わない。

## 許可scope

- src/loto/provider_sandbox/**
- tests/provider_sandbox/**
- docs/provider_sandbox/**
- configs/provider_sandbox/**
- scripts/run_provider_sandbox.py

provider固有pathは変更しない。

## 必須policy

- backend: BUBBLEWRAP / ROOTLESS_OCI / NONE
- untrusted_remote_code=trueの場合NONE禁止
- network disabled
- read-only root
- repository/model/input read-only
- output/tmpfsのみwritable
- no-new-privileges
- drop all capabilities
- PID/CPU/RAM/file/output/wall-time limit
- explicit GPU device allowlist
- safe mount containment
- symlink拒否
- environment allowlist
- secret pattern deny
- Docker socket、SSH agent、home、cloud credentials、DB/MLflow credentials禁止

## 実装方針

- shell文字列を生成せずargv配列
- backend detectorはinjected
- source pathとtarget pathを別検証
- requested policyとeffective evidenceを比較
- missing effective evidenceはPASSにしない
- fake child processでtimeout/nonzero/output-limitを検証
- target-host security certificationは行わない

## 必須tests

network default deny、secret env reject、path traversal、symlink、read-write model mount reject、
NONE reject、missing limits、GPU allowlist、command injection string、effective mismatch、
timeout、nonzero、oversized output、manifest tamper。

## 非主張

real kernel isolation=false
real bubblewrap execution=false
real OCI execution=false
provider migration=false
runtime certified=false
security certified=false
```
