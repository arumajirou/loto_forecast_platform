# Risk Register — GitHub Platform Features Foundation v1

| ID | Risk | Probability | Impact | Detection | Mitigation | Residual/owner |
|---|---|---:|---:|---|---|---|
| R-01 | Actions jobs fail before steps because Issue #58 remains unresolved | High | Critical | jobs API/UI shows no steps/logs | fix account/repository settings first; no repeated blind reruns | Owner: repository admin |
| R-02 | Private repository Pages site is assumed private but becomes public | Medium | Critical | plan/visibility review and external access test | explicit `docs-public/` allowlist; owner approval; disable deployment by default | Owner: repository admin/security |
| R-03 | Internal docs, Holdout/Prospective evidence, local paths, or secrets enter Pages artifact | Medium | Critical | pre-build audit, secret scan, manifest review | symlink/traversal rejection, blocked paths/terms, deployment gate | Owner: docs/security |
| R-04 | Dependabot updates Torch/CUDA/Transformers stack incompatibly | High | High | lock diff, import/runtime smoke, compatibility matrix | no auto-merge; dedicated review; isolated provider lanes | Owner: runtime lead |
| R-05 | Dependabot PR volume saturates CI/review capacity | Medium | Medium | open PR count and Actions usage | weekly schedule, groups, bounded PR limits | Owner: maintainer |
| R-06 | Project status is mistaken for registry or promotion authority | Medium | Critical | inconsistent state audit | explicit authority boundary; no production mutation handler | Owner: governance lead |
| R-07 | Project automation overwrites Failed/Partial evidence | Medium | High | field-transition audit | immutable Run IDs and evidence links; restricted transitions | Owner: governance lead |
| R-08 | Forged webhook accepted | Low/Medium | Critical | signature failure metrics and security tests | HMAC-SHA256 raw-body verification, constant-time compare, TLS | Owner: security |
| R-09 | Webhook replay or duplicate causes repeated side effects | Medium | High | duplicate/conflict metrics | unique delivery key, payload hash, idempotent handlers | Owner: integration lead |
| R-10 | Receiver acknowledges before durable persistence and loses event | Medium | High | failure injection | transactional store/outbox before 2xx | Owner: backend lead |
| R-11 | Receiver exceeds GitHub delivery timeout | Medium | Medium | acknowledgement latency histogram | no external calls in request path; queue handlers | Owner: backend lead |
| R-12 | Raw payload or signature is logged | Medium | Critical | log secret scan | normalized metadata only; structured redaction; tests | Owner: security |
| R-13 | SMTP/Slack/MLflow outage blocks authoritative event processing | Medium | Medium | adapter health and retry states | adapters are side effects; bounded retry/dead letter | Owner: operations |
| R-14 | MLflow linkage mutates model promotion or registry state | Low | Critical | integration contract tests/audit | reference-only handler; deny promotion APIs | Owner: MLOps lead |
| R-15 | CodeQL is added but unavailable for current owner/plan | High | Medium | entitlement/API/settings review | eligibility gate; clearly labelled OSS fallback | Owner: repository admin |
| R-16 | OSS scanner failure is reported as clean | Medium | High | exit-code and artifact completeness checks | scanner crash => FAILED; no empty-success report | Owner: security |
| R-17 | Workflow token permissions are excessive | Medium | High | workflow permission audit | explicit per-workflow least privilege; no blanket write | Owner: security |
| R-18 | Third-party Actions or MkDocs plugins introduce supply-chain risk | Medium | High | revision and provenance review | pin immutable revisions/versions; minimize plugins | Owner: dependency lead |
| R-19 | Generated artifacts or reports become too large for Git | Medium | Medium | size scan and diff review | upload Actions artifacts; keep summaries/manifests only | Owner: maintainer |
| R-20 | Settings changes cannot be reconstructed or rolled back | Medium | High | missing pre-change export | export settings/evidence before change; retain screenshots | Owner: repository admin |
| R-21 | `main` moves while implementation assumptions are stale | High | Medium | pre-branch audit and compare | rebase-free fresh branch from latest main; re-audit paths | Owner: PR author |
| R-22 | Parallel PRs modify shared workflows/root lock and conflict | High | Medium | branch/PR search and compare | ownership matrix; serialize shared-path changes | Owner: integration lead |
| R-23 | Security finding suppression becomes permanent technical debt | Medium | High | suppression inventory/age | reason, owner, scope, expiry/review date | Owner: security |
| R-24 | Webhook event store grows without retention controls | Medium | Medium | table size/queue metrics | normalized bounded records, retention and archival policy | Owner: operations |
| R-25 | Metrics use unbounded labels and overload Prometheus | Medium | Medium | cardinality audit | IDs and SHAs in logs/traces, not metric labels | Owner: observability |
| R-26 | Public docs imply predictive superiority or production certification | Medium | High | content review | preserve research disclaimer and evidence statuses | Owner: research lead |

## Review policy

- Review at each implementation PR and after any incident.
- Critical risks require an explicit acceptance, mitigation, or blocker decision before Ready transition.
- Closed risks retain evidence and are not deleted.
- New risks receive a unique ID; failed results and incidents are preserved under separate Run IDs.