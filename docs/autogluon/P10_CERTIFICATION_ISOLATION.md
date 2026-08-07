# AutoGluon P10 Certification Isolation Review

Status: `IMPLEMENTED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_PENDING`

## Finding

The runtime certification harness previously allowed a non-empty output directory. A
second execution could therefore encounter stale request, response, report, or model
artifact files from an earlier run. If the current provider failed before replacing a
response, stale evidence could be interpreted as current-run evidence.

The load scenario also ran even when its fit/save prerequisite had failed, producing a
secondary failure instead of preserving the dependency boundary.

## Remediation

The harness now:

- accepts only an absent or empty output directory;
- rejects an empty provider command and non-positive timeout;
- binds every response to the exact request run ID and operation;
- requires a positive provider PID;
- verifies requested and resolved device evidence;
- rejects GPU-use evidence in CPU scenarios;
- requires provider context, execution plan, and timeline mapping to remain inside the
  scenario artifact directory;
- records `explicit-naive-load` as `BLOCKED_RUNTIME` without execution unless
  `explicit-naive-fit` is verified in the same campaign.

## Local verification

- focused certification harness tests: 9 passed;
- related AutoGluon execution/provider tests: 34 passed total;
- Python compileall: PASS;
- lines over 100 characters in changed Python files: 0;
- exact remote Git blob equality: PASS.

Ruff, mypy, real AutoGluon 1.5.0 execution, full pytest, GitHub Actions, and GPU
certification remain pending and are not claimed as successful.
