# Prompt — Cross-PR Review and Integration Audit

```text
@GitHub

対象:
https://github.com/arumajirou/loto_forecast_platform

次のPR群をmergeせず、read-onlyで横断監査してください。

- Durable Run Lifecycle Contract v1
- Clock Health Gate v1
- Untrusted Provider Sandbox Contract v1
- Database Migration Foundation v1
- Persistence Outbox and Reconciliation v1
- Target-host Integration Fault Harness v1

## 再取得

default branch、latest main SHA、各PR head/base、changed files、diff、checks、reviews、
Issue、branch relationを取得する。

## 監査項目

1. PR #120〜#134および新規cross-cutting PRとのpath/semantic overlap
2. contract重複
3. status taxonomy矛盾
4. SHA-256 canonicalization差
5. UTC/time semantic差
6. Run ID/idempotency/fencing整合
7. migration dependency graph
8. outbox transaction boundary
9. SQLite-only false confidence
10. sandbox requested/effective evidence差
11. clock healthとtrusted timeの混同
12. fake/synthetic evidenceのformal昇格
13. Holdout/Prospectiveアクセス
14. root dependency/uv.lock conflict
15. rollbackとnon-claims
16. CI pre-run blockerの誤分類

## 出力

- INTEGRATION_AUDIT.md
- PATH_OWNERSHIP.csv
- CONTRACT_CONFLICTS.csv
- STATUS_TAXONOMY_MATRIX.csv
- PR_DEPENDENCY_DAG.json
- MERGE_ORDER_RECOMMENDATION.md
- BLOCKERS.md
- SHA256SUMS

merge、Ready、rebase、force push、branch updateを行わない。
```
