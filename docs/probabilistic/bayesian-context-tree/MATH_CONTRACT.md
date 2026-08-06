# Mathematical Contract for PR-B

PR-A contains no mathematical kernel. PR-B must implement and verify, without
copying upstream source:

1. finite-alphabet context counts;
2. suffix-closed context representation up to `max_depth`;
3. prior and posterior categorical probabilities;
4. exact log-space recursion for the exact lane;
5. MAP context-tree evidence and optional top-k tree evidence;
6. one-step prediction before observing or updating with the scored symbol;
7. unseen-context behavior with explicit backoff or posterior averaging;
8. missing-observation behavior that skips the update and resets context continuity;
9. exact save/resume continuation;
10. bounded-lane pruning evidence kept separate from exact-lane claims.

The exact lane forbids context and posterior-mass pruning. The bounded lane is an
approximate extension and must report every discarded context or probability
mass. A bounded-lane result must never be labeled exact.

Small binary and ternary sequences must agree with independently written manual
enumerations before any real-data runtime claim.
