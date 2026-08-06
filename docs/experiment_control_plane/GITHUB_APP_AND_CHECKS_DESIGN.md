# GitHub App and Check Runs Design

## App

Suggested name:

```text
Loto Experiment Controller
```

Authentication uses GitHub App installation tokens. Tokens are short-lived and scoped to selected
repositories and permissions.

## Responsibilities

- read reviewed plan content;
- create/update Check Runs;
- add bounded Issue/PR comments;
- update Project projection;
- receive re-request intent;
- create result-status references.

The App cannot merge, promote, register, deploy, or modify plan content.

## Check naming

Check names are stable, low-cardinality, and versioned only when semantics change.

## Check output

Each Check output contains:

```text
experiment_id
run_id
plan_sha256
gate
status
evidence_index_uri
evidence_sha256
verified_at_utc
non_claims[]
```

Annotations point to plan/result files, not to secret or large external payloads.

## Re-request

A re-request creates a new audited attempt or reconciliation action. It never deletes or rewrites
the previous result.

## Ruleset integration

After the App has produced reviewed checks, selected plan/result branches may require those checks
and restrict the accepted status source to this App. Settings changes occur in a separate PR/owner
operation.
