# Migration Plan — GitHub Platform Features Foundation v1

## 1. Migration strategy

Use additive, feature-flagged, independently reversible increments. No existing production binding, registry state, evaluation protocol, prediction lock, or data split is migrated by this initiative.

## 2. Pre-migration inventory

Before each implementation PR, capture:

- default branch and latest `main` SHA;
- branch and PR duplication search;
- `.github/**`, root dependency files, API routes, observability, registry, and security configuration;
- repository visibility, owner type, plan/feature eligibility;
- Actions settings, runner policy, billing/usage state;
- Pages setting and current deployment state;
- existing Project and webhook registrations;
- repository secrets/variables names only, never values;
- current workflow and status-check behavior.

## 3. Dependabot migration

### Forward

1. Add configuration on a dedicated branch.
2. Validate syntax and policy.
3. Merge after review.
4. Observe the first scheduled or manually triggered update cycle.
5. Classify generated PRs and confirm no auto-merge.

### Rollback

Revert the configuration PR or remove the file in a normal PR. Close generated Dependabot PRs only after review. Do not rewrite dependency history.

## 4. Projects migration

### Forward

1. Export any existing Project configuration.
2. Create fields and views using the documented taxonomy.
3. Enable built-in workflows one at a time.
4. Test with dedicated non-production Issue/PR fixtures.
5. Import active Issues/PRs in bounded batches.
6. Export final configuration and screenshots.

### Rollback

Disable automation first. Preserve Issues/PRs. Archive or delete the Project only with explicit owner approval. Project removal must not delete repository work items.

## 5. Pages migration

### Forward

1. Record visibility/plan decision.
2. Introduce `docs-public/` with a minimal landing page.
3. Add audit and strict local build.
4. Verify build artifact and manifest without deployment.
5. Add PR build workflow.
6. After Issue #58 recovery, add deployment workflow.
7. Enable repository Pages setting and environment approval.
8. Deploy minimal site, smoke test, then add public content incrementally.

### Rollback

1. Disable deployment workflow.
2. Disable Pages in repository settings.
3. Verify public URL no longer serves the site or shows the expected disabled state.
4. Preserve source, manifests, and incident evidence.
5. Rotate any credential exposed by content; content removal alone is insufficient.

## 6. Webhook migration

### Forward

1. Implement receiver disabled by default.
2. Run offline signed fixtures.
3. Add local persistent store and outbox.
4. Deploy receiver without registering GitHub webhook.
5. Verify health, TLS, metrics, logs, backup, and secret loading.
6. Create a high-entropy webhook secret in approved secret storage.
7. Register webhook with minimal event allowlist.
8. Send GitHub test delivery and verify end-to-end evidence.
9. Enable handlers one at a time: workflow status, email, Project sync, MLflow reference.

### Data migration

No historical raw payload import by default. Historical event backfill, when required, uses normalized metadata from GitHub API and separate Run IDs; it is never represented as originally received webhook evidence.

### Rollback

1. Disable handlers.
2. Disable/delete webhook registration after exporting configuration metadata.
3. Disable endpoint with feature flag or routing rule.
4. Drain or dead-letter queued events deterministically.
5. Preserve delivery/audit records under retention policy.
6. Rotate webhook secret.

## 7. Security scanning migration

### Forward

1. Establish baseline using local OSS scans.
2. Triage findings without mass suppression.
3. Add workflow after Issue #58 recovery.
4. Add required checks only after stable evidence.
5. Enable CodeQL separately after eligibility approval.

### Rollback

Remove required-check enforcement before disabling a workflow. Preserve historical findings and reasons. Do not mark unresolved findings fixed merely because a scanner is disabled.

## 8. Database migration controls

Webhook schema migrations use versioned forward and downgrade scripts, transactional application, pre-migration backup, row-count/hash checks where applicable, and a tested restore procedure. A database migration never shares a transaction with external email, Project, or MLflow calls.

## 9. Secret migration and rotation

- Secret values are created only in approved secret storage.
- Names and purpose may be documented; values may not.
- Webhook secret rotation supports active and previous key IDs for a bounded period.
- SMTP and integration credentials have separate identities and scopes.
- Rollback includes revocation/rotation, not only code revert.

## 10. Completion criteria

Migration completes only after forward behavior, rollback behavior, observability, manifests, security checks, and operator handoff are verified. A merged configuration file without runtime evidence remains `IMPLEMENTED_NOT_VERIFIED`.