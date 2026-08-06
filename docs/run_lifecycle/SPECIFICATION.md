# Functional Specification

## Initial state

Every new Run starts at:

```text
phase=PLAN
status=PENDING
revision=0
last_event_sha256=null
```

## State progression

A normal phase uses two explicit commands:

```text
<PHASE>/PENDING --START--> <PHASE>/RUNNING
<PHASE>/RUNNING --MARK_SUCCEEDED--> <NEXT_PHASE>/PENDING
```

`PROMOTE/RUNNING --MARK_SUCCEEDED--> COMPLETE/SUCCEEDED` is terminal. Cancellation is accepted only
through `CANCEL`. `CANCELLED`, `TERMINAL_FAILURE`, and `COMPLETE/SUCCEEDED` are immutable.

## Failure and recovery states

```text
RUNNING --MARK_RETRYABLE_FAILURE--> RETRYABLE_FAILURE --RETRY--> RUNNING
RUNNING --MARK_BLOCKED-----------> BLOCKED -----------> RESUME --> RUNNING
RUNNING --MARK_TIMED_OUT---------> TIMED_OUT ---------> RESUME --> RUNNING
RUNNING --MARK_TERMINAL_FAILURE--> TERMINAL_FAILURE
```

The phase does not change for failure/retry/resume transitions. Therefore states such as
`PERSIST + RETRYABLE_FAILURE` remain representable.

## Command execution

1. Compute effective idempotency key and independent command fingerprint.
2. Return the previous verified result when the same semantic command already exists.
3. Reject the same declared key with a different fingerprint.
4. Validate active lease and fencing token when worker lease fields are supplied.
5. Decide the transition from the centralized matrix.
6. Skip the handler when all requested output names are already sealed.
7. Build and hash the next event.
8. Atomically commit event, aggregate and idempotency record in the in-memory repository.

## Event hash

The event hash covers every event field except `event_sha256` itself. List order is meaningful. UTC
datetimes use a normalized `Z` representation. Recalculation is mandatory during validation.

## Idempotency identity

Included:

- schema version;
- Run ID;
- command type;
- phase;
- expected revision;
- subject hashes;
- semantic parameters;
- requested output names.

Excluded:

- issued timestamp;
- command/request identity;
- actor identity;
- lease ID and owner;
- fencing token;
- attempt/process/PID/trace fields.

## Lease semantics

An unexpired lease cannot be taken over. After expiry, a new owner receives a strictly greater
fencing token. A mutation must match the active Run ID, lease ID, owner, expiry and latest fencing
token.
