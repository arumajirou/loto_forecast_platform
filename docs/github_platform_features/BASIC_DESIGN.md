# Basic Design — GitHub Platform Features Foundation v1

## 1. Architectural principles

1. **Separate control planes:** GitHub governance, model registry, promotion, experiment tracking, and production binding remain separate authoritative domains.
2. **Least privilege:** each workflow and endpoint receives only required permissions.
3. **Fail closed:** missing signatures, uncertain visibility, unavailable persistence, and unverified eligibility block activation.
4. **Evidence before claims:** availability, workflow presence, or UI visibility does not equal successful execution.
5. **Independent rollback:** Dependabot, Projects, Pages, Webhooks, and security scanning can be disabled independently.
6. **No hidden fallback:** CodeQL fallback, CPU fallback, notification degradation, and MLflow unavailability are explicitly classified.

## 2. Logical architecture

```text
                    +----------------------+
                    | GitHub Repository    |
                    | Issues / PRs / Push  |
                    +----------+-----------+
                               |
             +-----------------+------------------+
             |                 |                  |
             v                 v                  v
     +---------------+  +---------------+  +----------------+
     | Dependabot    |  | GitHub Project|  | GitHub Actions |
     | uv / actions  |  | governance    |  | isolated lanes |
     +---------------+  +---------------+  +-------+--------+
                                                       |
                                      +----------------+----------------+
                                      |                |                |
                                      v                v                v
                               docs build/deploy  security scans   CI evidence

 GitHub Webhook
       |
       v
+-----------------------+
| FastAPI receiver      |
| body limit            |
| HMAC verification     |
| event schema          |
+-----------+-----------+
            |
            v
+-----------------------+
| Event store / outbox  |
| delivery dedup        |
| audit + retry state   |
+-----------+-----------+
            |
      +-----+----------------+----------------+
      |                      |                |
      v                      v                v
 email adapter        Project sync      MLflow reference
 (default)            (non-authority)   (no promotion write)
```

## 3. Repository layout

```text
.github/
  dependabot.yml
  workflows/
    ci.yml                         # existing, unchanged by foundation
    docs-build.yml
    pages-deploy.yml
    security-fallback.yml
    codeql.yml                     # future eligibility-gated

docs-public/                       # explicit public allowlist
mkdocs.yml
scripts/docs/
  audit_public_docs.py
  build_public_docs.py
scripts/security/
  run_security_checks.py
src/loto/integrations/github_webhook/
  contracts.py
  signature.py
  receiver.py
  store.py
  outbox.py
  router.py
  metrics.py
  handlers/
    email.py
    project_sync.py
    workflow_status.py
    mlflow_reference.py
tests/integrations/github_webhook/
docs/github_platform_features/
```

## 4. Workflow separation

| Workflow | Trigger | Permissions | Purpose |
|---|---|---|---|
| `ci.yml` | push, pull_request | contents read | existing Ruff/compileall/pytest lane |
| `docs-build.yml` | PR paths | contents read | audit and strict build only |
| `pages-deploy.yml` | main paths/manual | contents read, pages write, id-token write | approved public deployment |
| `security-fallback.yml` | PR/main/schedule/manual | contents read, security-events write only if supported | OSS scanning artifacts |
| `codeql.yml` | future | required CodeQL permissions | eligibility-gated code scanning |

Heavy workflows must not be triggered by every documentation or metadata-only change unless required by repository rules. Path filters and concurrency groups are mandatory.

## 5. Data ownership

| Data | Owner/source of truth | GitHub integration access |
|---|---|---|
| Issue/PR lifecycle | GitHub | read/update governance fields |
| Project status | GitHub Project | workflow status only |
| experiment metrics | MLflow/DB/artifacts | reference/link only |
| model registry | PlatformRegistry | no direct mutation in foundation |
| promotion/approval | promotion subsystem | no direct mutation |
| webhook delivery | integration event store | create/update processing state |
| public documentation | reviewed Git tree | build/deploy only |

## 6. Security zones

- **Public zone:** generated Pages artifact from `docs-public/`.
- **Repository zone:** private source, Issues, PRs, workflow metadata.
- **Integration zone:** webhook receiver and event store.
- **Experiment zone:** MLflow, databases, artifacts, prediction locks.
- **Secret zone:** GitHub Actions secrets, webhook secret, SMTP credentials; never logged or exported.

## 7. Availability and degradation

- Actions unavailable: Dependabot may still create PRs, but Actions-dependent validation and Pages deployment remain blocked.
- Project unavailable: Issues and PRs remain authoritative; manual backlog view is used.
- Webhook receiver unavailable: GitHub delivery is recorded as failed by GitHub; operator follows redelivery runbook.
- Email unavailable: event processing succeeds with notification status `FAILED` or `RETRY_WAIT`.
- MLflow unavailable: GitHub event remains durable; linkage retries without promotion side effects.

## 8. Promotion boundary

No GitHub event, Project field, Dependabot PR, Pages deployment, security alert, email, or MLflow tag may independently promote a model, approve a candidate, open Holdout, bind production, or alter prediction-lock evidence.