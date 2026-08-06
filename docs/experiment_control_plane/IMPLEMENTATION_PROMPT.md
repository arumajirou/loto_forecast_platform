# Prompt — Experiment Plan Contract v1

```text
@GitHub

対象リポジトリ:
https://github.com/arumajirou/loto_forecast_platform

設計branch:
docs/experiment-control-approval-evidence-index-blueprint-v1

あなたは実験管制、承認、ローカルLLM／プロプライエタリAPI実行、
証拠索引を担当するリードエンジニアです。

## 共通安全規則

- 設計branchはread-only入力であり、実装branchのbaseにしない。
- 実行直前にdefault branchとlatest main SHAを再取得する。
- 同一目的のbranch、open/closed PR、Issue、packageを再検索する。
- PR #121、#123以降および新規cross-cutting PRを再監査する。
- PR #137 Promotion、#139 GitHub platform features、#140 durable lifecycle、
  #141 telemetryの責務をコピーまたは再定義しない。
- 重複または意味的所有権衝突時はbranchを作らず停止する。
- latest mainから独立branchを作成する。
- main直接変更、force push、rebase、reset、history rewrite、Ready、merge、
  auto-merge、branch削除を禁止する。
- dirty worktreeを変更しない。
- Holdout、Prospective Actual、production Registry/Promotionを開かない。
- 実行していない検証をPASSと書かない。
- Actionsにstep/logがない場合はCI_BLOCKED_RUNNER_STARTと分類する。

TARGET_PR=Experiment Plan Contract v1
IMPLEMENTATION_BRANCH=feat/experiment-plan-contract-v1
PR_MODE=Draft

## 設計入力

設計branchから次を全文取得し、SHA256SUMSを検証してください。

docs/experiment_control_plane/README.md
docs/experiment_control_plane/REQUIREMENTS.md
docs/experiment_control_plane/FUNCTIONAL_SPECIFICATION.md
docs/experiment_control_plane/BASIC_DESIGN.md
docs/experiment_control_plane/DETAILED_DESIGN.md
docs/experiment_control_plane/ARCHITECTURE.md
docs/experiment_control_plane/DATA_CONTRACT.md
docs/experiment_control_plane/APPROVAL_POLICY.md
docs/experiment_control_plane/EXECUTION_LANES.md
docs/experiment_control_plane/SECURITY_MODEL.md
docs/experiment_control_plane/TEST_PLAN.md
docs/experiment_control_plane/TRACEABILITY_MATRIX.md
docs/experiment_control_plane/ARTIFACT_MANIFEST.json
docs/experiment_control_plane/SHA256SUMS

不一致時は実装せず停止してください。

## 今回の目的

実験開始前の正式なExperiment Plan、Approval requirement、Execution lane、
Evaluation、Baseline、Seed、Budget、Protected stage、Evidence requirementを
strict Pydantic v2 contractとして実装してください。

今回はGitHub API、Issue Form、Actions workflow、Project、GitHub App、
Local Agent、MLflow、PostgreSQL、Object Storage、実モデル実行を行いません。

## 許可scope

src/loto/experiment_control/**
tests/experiment_control/**
docs/experiment_control/**
configs/experiment_control/**

既存ファイル、root pyproject.toml、uv.lock、workflowを変更しないでください。
必要と判断した場合は実装せず理由を報告してください。

## 必須contract

- ExperimentId
- ExperimentPlan
- ExperimentIdentity
- HypothesisContract
- CodeBinding
- DataBinding
- ModelBinding
- ExecutionLane
- ExecutionPolicy
- SeedPolicy
- EvaluationContract
- BaselineInventory
- SearchBudget
- ResourceBudget
- ProtectedStagePolicy
- ApprovalRequirement
- EvidenceRequirement
- ExperimentPlanValidationFinding
- ExperimentPlanValidationReport

全modelは原則:
ConfigDict(extra="forbid", strict=True, frozen=True,
           validate_default=True, allow_inf_nan=False)

## 必須policy

- primary metricはHIT_AT_1固定
- POSITION_HIT_AT_1、ALL_POSITIONS_HIT_AT_1、MAE、MSE、RMSE必須
- RANDOM、FIXED、MEAN、MEDIAN、LAST、FREQUENCY、STATISTICAL baseline必須
- best_seed_only_selection=false
- first_place_only_selection=false
- seed一覧は空でなくunique
- mean、population variance、worst必須
- Train/Validation/Holdout/Prospectiveの時間順序
- scaler/encoder/feature selection/HPOはTrain内だけ
- Holdout/Prospectiveはauto_open=false、approval required
- formal model/code revisionはimmutable
- requested deviceとCPU fallback policyを分離
- laneはLOCAL_CPU / LOCAL_GPU / API_PAID
- API_PAIDはrequest/token/time/cost cap必須
- formal GPUは既定で同時1件
- worker上限8
- required evidence inventory
- plan SHA-256 canonicalization
- result-affecting field変更でplan hash変更
- timestamp、Issue更新時刻、PR番号はsemantic hashから除外

## Canonical JSON

UTF-8、sort_keys=true、separators=(",", ":")、ensure_ascii=false、
UTC Z、finite numberのみ、duplicate JSON key拒否、bytes/set/tuple拒否。
自己hash fieldだけをhash対象外にする。

## 必須negative tests

unknown field、型coercion、bool/int、naive datetime、uppercase/malformed SHA、
NaN/Inf、重複seed、空seed、best-seed true、first-place true、primary metric変更、
secondary不足、baseline不足、時間順違反、Train外fit/HPO、protected stage自動開封、
unpinned revision、API予算不足、worker>8、formal GPU concurrency>1、
credential-bearing URI、plan hash tamper。

Hypothesis property testsでcanonicalizationとhash感度を検証してください。

## 成果物

README、REQUIREMENTS、SPECIFICATION、ARCHITECTURE、DATA_CONTRACT、
TEST_PLAN、VERIFICATION_REPORT、CHANGELOG、HANDOFF、RUNBOOK、
ARTIFACT_MANIFEST.json、SHA256SUMS。

## 非主張

GitHub integration=false
Issue Form=false
Project=false
GitHub App=false
Local Agent=false
real execution=false
database=false
MLflow=false
Holdout=false
Prospective=false
Promotion=false
production eligibility=false

## 検証順

focused pytest
property tests
compileall
AST/JSON/YAML parse
secret/line-length scan
manifest/SHA256SUMS
Ruff
mypy
related config/evaluation regression
full pytest last

Draft PRのまま終了してください。
```
