# Functional Specification — GitHub Platform Features Foundation v1

## 1. Scope boundary

This specification defines behavior and contracts. It does not enable repository settings, publish a Pages site, create Project fields, register a webhook, add secrets, or change production state.

## 2. Capability matrix

| Capability | Foundation status | Activation gate | Authoritative state |
|---|---|---|---|
| Dependabot | DESIGN_READY | dedicated PR merged | GitHub dependency graph and reviewed lock |
| GitHub Projects | DESIGN_READY | owner creates/configures Project | Issues and PRs; not model registry |
| Pages | BLOCKED_PENDING_VISIBILITY_DECISION | approved public allowlist and Actions recovery | built commit and Pages deployment |
| Webhook receiver | DESIGN_READY | endpoint, secret, queue, tests, deployment | receiver database/outbox plus GitHub delivery ID |
| OSS security scanning | DESIGN_READY | Actions recovery or local runner evidence | retained scanner reports |
| CodeQL | BLOCKED_BY_ELIGIBILITY | organization/plan/Code Security approval | GitHub code-scanning alerts |

## 3. Dependabot behavior

### Inputs

- `/pyproject.toml`
- `/uv.lock`
- `/.github/workflows/**`

### Outputs

- bounded update pull requests;
- dependency diff and lock diff;
- compatibility-review checklist;
- labels and reviewer assignment where configured.

### Rules

1. Run weekly, not continuously.
2. Limit concurrent update PRs to prevent CI and reviewer saturation.
3. Group low-risk compatible updates only when the resulting lock remains reviewable.
4. Treat Python, Torch, Triton, Transformers, NeuralForecast, Ray, MLflow, CUDA-related packages, and remote-code providers as compatibility-sensitive.
5. Never enable automatic merge in the foundation or first implementation increment.
6. Dependabot availability is not proof that a dependency update is safe or runtime-certified.

## 4. Project governance behavior

### Fields

- `Status`
- `Workstream`
- `Type`
- `Priority`
- `Evidence Status`
- `PR Phase`
- `Provider`
- `Risk`
- `Base SHA`
- `Protocol Hash`
- `Target Release`

### Status transitions

```text
Intake -> Spec -> Design -> Ready -> In Progress -> Verification -> Done
                         \-> Blocked
Verification -> Failed -> In Progress or Closed
```

Transitions must preserve prior evidence in comments, PR descriptions, artifacts, or issue history. A card movement must not overwrite a failed Run ID or retroactively promote an unverified model.

### Built-in automation

- opened Issue/PR -> add to Project;
- merged PR or closed Issue -> `Done`;
- `blocked` label -> `Blocked`;
- Draft PR -> `In Progress` or `Verification`, depending on evidence status;
- archive only after retained completion evidence.

## 5. Pages behavior

### Source policy

Only files reachable from `docs-public/` are site inputs. Symlinks are prohibited. The build must reject traversal, generated links to internal files, absolute local paths, secrets, unapproved external embeds, and files larger than the configured documentation limit.

### Build pipeline

```text
PR change -> public-doc audit -> strict static build -> link check -> artifact
main merge -> repeat audit/build -> deploy Pages artifact -> smoke check
```

### Required pages

- project purpose and disclaimer;
- public architecture overview;
- public API overview;
- model catalog summary without private runtime evidence;
- evaluation methodology;
- installation and usage instructions safe for public disclosure;
- security contact and disclosure policy.

### Prohibited content

- `runs/**`, `artifacts/**`, logs, raw databases;
- tokens, credentials, callback URLs, private hostnames;
- Holdout or Prospective actuals and sealed predictions before authorized disclosure;
- unreviewed remote code or model files;
- private issue/PR content copied without approval;
- local absolute paths and user names.

## 6. Webhook receiver behavior

### HTTP contract

```text
POST /api/v2/integrations/github/webhook
Content-Type: application/json
X-GitHub-Event: <event>
X-GitHub-Delivery: <uuid>
X-Hub-Signature-256: sha256=<hex>
```

### Response contract

- `202 Accepted`: new valid delivery persisted and queued;
- `200 OK`: valid duplicate already accepted;
- `400 Bad Request`: malformed headers or body;
- `401 Unauthorized`: signature missing or invalid;
- `413 Payload Too Large`: configured body limit exceeded;
- `415 Unsupported Media Type`: unsupported content type;
- `422 Unprocessable Entity`: unsupported or invalid event schema;
- `503 Service Unavailable`: persistence unavailable before acknowledgement.

### Event record

```json
{
  "delivery_id": "uuid",
  "event_type": "pull_request",
  "action": "opened",
  "repository_id": 1317186795,
  "repository_full_name": "arumajirou/loto_forecast_platform",
  "sender_login": "masked-or-validated-login",
  "ref": null,
  "head_sha": "40-hex-sha-or-null",
  "payload_sha256": "64-hex",
  "received_at": "2026-08-06T07:00:00Z",
  "signature_verified": true,
  "processing_status": "QUEUED",
  "attempt": 0,
  "trace_id": "trace-id"
}
```

### Processing states

```text
RECEIVED -> VERIFIED -> QUEUED -> PROCESSING -> SUCCEEDED
                                  \-> RETRY_WAIT -> PROCESSING
                                  \-> DEAD_LETTER
RECEIVED -> REJECTED
```

### Initial handlers

- `pull_request`: governance/status notification only;
- `issues`: Project and email notification metadata;
- `workflow_run`: CI status ingestion without treating zero-step failure as code failure;
- `push`: changed-path evaluation and documentation/deployment trigger metadata.

## 7. Notification behavior

Email notifications are generated from normalized event records. Raw request bodies are not included. Notifications include repository, event, action, branch/ref, SHA, status, GitHub URL, UTC timestamp, and trace/delivery identity. Slack integration is a disabled optional adapter.

## 8. MLflow linkage behavior

A handler may attach Git identity and verification references to an existing MLflow run or create a dedicated integration run. It must not change champion, registry, promotion, approval, or production binding. Missing MLflow connectivity results in a bounded retry or `PARTIALLY_VERIFIED` notification state, not loss of the GitHub event.

## 9. Security scanning behavior

### Fallback lane

- dependency audit: `pip-audit` or equivalent against resolved environment/lock;
- Python SAST: Bandit and/or Semgrep rules fixed by revision;
- secret detection: detect-secrets plus repository-specific allowlist review;
- workflow/YAML validation;
- license and provenance inventory.

### CodeQL lane

CodeQL is enabled only after eligibility verification. It runs in a separate workflow with least privilege, independent from the existing heavyweight test workflow. Findings are not silently dismissed; suppressions require reason, owner, scope, and expiry/review date.