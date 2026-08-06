# Approval Model

## Separate approval scopes

```text
PLAN_ACCEPT       accept the immutable plan into the repository
EXECUTE           enqueue one bounded execution subject
OPEN_HOLDOUT      authorize designated Holdout access
SCORE_PROSPECTIVE authorize scoring after trusted Prediction Lock and Actual verification
ACCEPT_RESULT     accept reviewed result/evidence summary
PUBLISH_CAMPAIGN  publish an approved campaign-level release
REQUEST_PROMOTION hand an immutable candidate to promotion governance
CANCEL_RUN        request cancellation of an active run
```

Approval in one scope never implies another.

## Subject binding

An approval binds:

```text
scope
plan_sha256
code/config/data/protocol/model identities
execution lane and budgets
requested action and constraints
target Run ID when the scope is run-specific
```

Any mutation produces a new subject hash and requires a new approval.

## Plan acceptance versus execution

- Merging a Plan PR records `PLAN_ACCEPT` only.
- `EXECUTE` requires an explicit ApprovalRecord plus a manual dispatch/API enqueue action.
- A Project field, label, reaction, comment text or PR merge alone is not an `EXECUTE` ApprovalRecord.

## Actor policy

Preferred organization mode:

```text
Requester != Approver
Approver has explicit role
Paid API / Holdout / Prospective / Promotion require higher assurance
```

Current personal-repository fallback:

- the owner may be both requester and approver only when no second authorized reviewer exists;
- the record must state `separation_of_duties=false` and `assurance=OWNER_SINGLE_ACTOR`;
- paid API, Holdout, Prospective and promotion can require an external second-person receipt before policy allows them;
- migration to an organization is recommended when granular roles are needed.

## Expiry and revocation

- Approvals have bounded expiry; no unlimited execution approval.
- Revocation is append-only and references the original approval.
- A queued but not leased request is cancelled on revocation.
- An active run follows explicit policy: cancel, quarantine result, or allow completion but block acceptance.
- Revocation never deletes audit/evidence history.

## One-time and replay control

An ApprovalRecord may declare `max_uses=1`. The controller consumes usage atomically with enqueue. Repeated identical client calls return the same enqueue receipt; they do not consume another use or create another run.

## Approval evidence in GitHub

GitHub may show a human-readable approval summary and Check status, but the canonical ApprovalRecord is stored in the control-plane repository/database and exported as a signed or hash-chained record. GitHub UI state is not sufficient proof by itself.
