# GitHub Visual Dashboard / Pages Runbook

```text
component: github-visual-dashboard
scope: repository observability and evidence navigation
pages_site_state: BLOCKED_BY_REPOSITORY_ENABLEMENT
holdout: CLOSED
prospective: CLOSED
automatic_promotion: FORBIDDEN
```

## Purpose

The visual dashboard turns the repository control-plane state into one browsable static site without
turning catalog availability into runtime or scientific success.

The site combines:

- current `main` SHA;
- open Issue and PR counts;
- active workflow count and workflow inventory;
- the unified canonical model inventory;
- the six canonical games;
- a Model × Game planning matrix;
- explicit Holdout, Prospective, and promotion boundaries.

## Status semantics

Every Model × Game cell starts as `UNASSESSED`.

`UNASSESSED` means only that no exact runtime-evidence record was supplied to the dashboard build.
It does **not** mean runtime failure, unsupported, non-routable, inaccurate, or rejected.

A cell can change only when an evidence record matches both the canonical `model_id` and `game`.
Allowed runtime display states are:

- `RUNTIME_CERTIFIED`;
- `RUNTIME_FAILED`;
- `BLOCKED`;
- `UNSUPPORTED`;
- `NON_ROUTABLE`.

Unknown model/game pairs, duplicate evidence records, duplicate model IDs, unsupported statuses, or
cross-product mismatches fail the dashboard build instead of silently changing status.

## Current planning matrix

The current identity planner reports:

- unified canonical model identities: `250`;
- canonical games: `6`;
- planning cross-product: `1,500` Model × Game cells.

These are planning units, not 1,500 successful executions.

Until a normalized runtime-evidence export is connected, the production build intentionally renders
all 1,500 cells as `UNASSESSED`.

## Build workflow

Workflow:

```text
00 / visual dashboard build
```

The normal build path:

1. verifies the self-hosted Linux runner;
2. creates an isolated Python 3.13 / uv environment;
3. installs CPU-only PyTorch and repository dependencies;
4. regenerates live GitHub observability JSON;
5. regenerates the canonical execution-identity plan;
6. builds the static site;
7. verifies the 250 × 6 planning boundary and formal scientific gates;
8. runs focused dashboard tests;
9. uploads the complete site as a short-lived Actions artifact;
10. verifies that the repository worktree stayed clean.

The build path does not require GitHub Pages to be enabled.

## Pages deployment gate

GitHub Pages is not currently configured for this repository. The repository Pages endpoint returned
`404` during the implementation audit.

Deployment is therefore explicit and fail-closed. The workflow has a `deploy_pages` boolean input,
and the Pages deployment job runs only when the workflow is manually dispatched with that input set
to `true`.

The deployment job uses immutable action pins and requests Pages/OIDC permissions only on that job.
It does not use `configure-pages` implicit enablement.

Before the first deployment, enable repository Pages with **GitHub Actions** as the publishing source:

1. open repository **Settings**;
2. open **Pages**;
3. set the build/deployment source to **GitHub Actions**;
4. run `00 / visual dashboard build` manually with `deploy_pages=true`;
5. verify the returned Pages URL and the deployed `dashboard.json` before calling the site live.

Do not mark `PAGES_SITE=LIVE` from workflow configuration alone.

## Runtime evidence overlay contract

An optional runtime evidence file has schema version 1:

```json
{
  "schema_version": 1,
  "records": [
    {
      "model_id": "canonical-model-id",
      "game": "numbers3",
      "status": "RUNTIME_CERTIFIED",
      "evidence_ref": "run://immutable-evidence-reference",
      "git_sha": "full-git-sha"
    }
  ]
}
```

The dashboard builder never derives runtime status from `available`, Project state, Issue labels,
workflow existence, or catalog counts.

## Security and rendering boundary

The static client has no external JavaScript or CSS CDN dependency. Dynamic repository values are
inserted through DOM text nodes / `textContent`, not dynamic `innerHTML`.

The dashboard is a navigation and evidence-index surface. Immutable run artifacts, SHA-256 manifests,
prediction locks, runtime certification evidence, and scientific evaluation artifacts remain the
formal sources of truth.

## Scientific boundary

The visual dashboard does not open or evaluate Holdout or Prospective data and cannot perform model
promotion. The formal dashboard values remain:

```text
Holdout              CLOSED
Prospective          CLOSED
Automatic promotion  FORBIDDEN
```
