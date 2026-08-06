# GitHub Implementation Prompts

## Prompt 1: Evaluation Protocol Completeness v1

```text
@GitHub

対象リポジトリ:
https://github.com/arumajirou/loto_forecast_platform

あなたは評価プロトコル、統計的比較、再現性を担当するリードエンジニアです。

TARGET_PR=Evaluation Protocol Completeness v1
BRANCH=fix/evaluation-protocol-completeness-v1
PR_MODE=Draft

docs/observability_expansion/ の REQUIREMENTS.md、FUNCTIONAL_SPECIFICATION.md、
BASIC_DESIGN.md、DETAILED_DESIGN.md、TEST_PLAN.md に従ってください。

開始前に latest main、同名branch、open/closed PR、Issue、PR #121、#123、#124、#127、#128、#129、
次の既存実装を再取得してください。

- src/loto/evaluation/**
- src/loto/orchestration/research_v3.py
- src/loto/contracts_general.py
- tests/evaluation/**
- tests/test_integrated_full_features.py

同一目的の実装があれば新規作業を停止し、重複監査だけを報告してください。

目的:
1. Hit@±1をcanonical primary metricにする。
2. legacy metric名を明示aliasで扱う。
3. result-affecting設定をprotocol v2へ含める。
4. comparison budget hashを追加する。
5. field-level protocol diffを追加する。
6. 全seedのmean、population variance、worst value、worst seedを保存する。
7. Random、fixed、mean、median、last、frequency、統計baseline inventoryを固定する。
8. historical artifactを書き換えない。

禁止:
- Holdout/Prospectiveアクセス
- model provider変更
- Runtime Certification再定義
- Data Access Ledger再定義
- root dependency追加
- workflow変更
- custom UI実装
- merge/Ready/auto-merge/force push

focused testを優先し、Ruff、mypy、関連回帰、full pytestは最後に実行してください。
未実行をPASSと書かないでください。
GitHub Actionsがsteps作成前に失敗した場合はCI_BLOCKED_RUNNER_STARTと分類してください。
Draft PR本文にはbase/head SHA、protocol field一覧、legacy compatibility、tests、non-claimsを記載してください。
```

## Prompt 2: Telemetry Contract v1

```text
@GitHub

対象リポジトリ:
https://github.com/arumajirou/loto_forecast_platform

あなたはObservability Contract担当リードエンジニアです。

TARGET_PR=Telemetry Contract v1
BRANCH=feat/telemetry-contract-v1
PR_MODE=Draft

このPRでは外部サービスを起動せず、共通のイベント、相関、redaction、
Prometheus metric定義とcardinality規則だけを実装してください。

開始前にPR #127、#123、#124/#129、mainのlogging、metrics、experiment tracking、
API request ID実装を再監査してください。

変更範囲:
- src/loto/telemetry/**
- tests/telemetry/**
- docs/telemetry/**

実装:
- strict EventEnvelope
- bounded enums
- contextvarsによるrequest_id/run_id等
- secret redaction
- payload size limit
- metric descriptor registry
- prohibited label検査
- isolated CollectorRegistry tests
- non-claim status

変更禁止:
- /livez、/readyz、/health/dependencies
- PR #127のrequest ID semantics
- OTel exporter
- Grafana/Loki/Tempo deployment
- provider code
- Holdout/Prospective
- pyproject/uv.lock
- workflow

秘密、DSN、protected actualがeventへ残るtestを必須にしてください。
```

## Prompt 3: OpenTelemetry Instrumentation v1

```text
@GitHub

TARGET_PR=OpenTelemetry Instrumentation v1
BRANCH=feat/otel-instrumentation-v1
PR_MODE=Draft

Telemetry Contract v1がmainへ統合済みであることを最初に確認してください。
未統合なら実装を停止してください。

FastAPI、HTTPX、SQLAlchemyの公式OpenTelemetry instrumentationと、
forecast domainのmanual spanを実装してください。

必須span:
data.load, data.validate, split.create, feature.fit, feature.transform,
model.load, model.fit, model.predict, prediction.lock, actual.read,
evaluation.score, artifact.persist, registry.persist, promotion.evaluate

要件:
- OTLP exporterはbounded timeoutとbatch queue
- default disabled
- protected actual、DSN、tokenをattributeへ入れない
- trace_idをstructured logsへ関連付ける
- in-memory exporter tests
- local collector smoke
- exporter unavailable時のDEGRADED_TELEMETRY
- formal audit event failureとoptional telemetry failureを区別

依存変更は独立commitで行い、uv.lockを更新してください。
```

## Prompt 4: Grafana Alloy / LGTM Operations v1

```text
@GitHub

TARGET_PR=Grafana Alloy LGTM Operations v1
BRANCH=ops/grafana-alloy-lgtm-v1
PR_MODE=Draft

独自UIを作らず、Grafana Alloy、Prometheus、Loki、Tempo、Grafanaの
deployment assets、provisioning、dashboards、alerts、runbookだけを実装してください。

PR #79のファイルは参考にしてよいが、branchが古いためcopy/mergeせず、
latest mainから再設計してください。

必須:
- loopback/default-private exposure
- secret-free configs
- persistent volumes
- retention
- resource limits
- health checks
- Grafana datasource provisioning
- dashboards as code
- alert runbooks
- restart smoke
- Loki log query
- Tempo trace query
- metric-log-trace correlation
- ARTIFACT_MANIFESTとSHA256SUMS

このPRでproduction deployment成功を主張しないでください。
```

## Prompt 5: MLflow Live Certification v1

```text
@GitHub

TARGET_PR=MLflow Live Certification v1
BRANCH=feat/mlflow-live-certification-v1
PR_MODE=Draft

既存のMLflow bridge、PostgreSQL tracking、Registry関連PRを再監査し、
新しいtracking schemaを重複作成しないでください。

非Holdoutの小規模Runで実PostgreSQL-backed MLflowを検証してください。
config/data/code/protocol hashes、git commit、model revision、全seed、
mean/variance/worst、prediction artifact、runtime evidence URIを保存してください。

必須:
- server start
- bounded write/read
- UIでRun比較
- process restart後のread
- backup/restore drill
- credentials redaction
- failure classification
- no Holdout/Prospective
- no promotion
```

## Prompt 6: Pandera Data Contracts v1

```text
@GitHub

TARGET_PR=Pandera Data Contracts v1
BRANCH=feat/pandera-data-contracts-v1
PR_MODE=Draft

Panderaの公式repositoryと最新互換versionを再確認し、
依存追加とuv.lock更新を行ってください。

対象境界は次の4つだけです。
1. Raw -> Normalized
2. Normalized -> Split
3. Prediction -> Scoring
4. Metrics -> Persistence

Feature Availability Registry、Data Access Ledger、Strict Configの責務を再実装しないでください。
列、dtype、null、range、uniqueness、chronology、finite値、actual presence policyを検証してください。
```

## Prompt 7: Evidently Quality Monitoring v1

```text
@GitHub

TARGET_PR=Evidently Quality Monitoring v1
BRANCH=feat/evidently-quality-monitoring-v1
PR_MODE=Draft

Evidentlyの公式OSS、license、API互換性を再確認してください。
独自dashboardを作らず、immutable snapshot adapterとEvidently reportを実装してください。

対象:
- normalized data quality
- feature/prediction drift
- data freshness
- delayed actual performance
- position Hit@±1
- all-position Hit@±1
- MAE
- baseline delta

source dataを変更しないこと。
actual reveal前にperformance reportを生成しないこと。
UI deploymentはreport生成検証後の別gateとしてください。
```
