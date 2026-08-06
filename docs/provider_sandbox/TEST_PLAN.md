# Test Plan

Run order:

```text
schema and policy tests
-> path and environment negative tests
-> argv tests
-> fake-child timeout/nonzero/output tests
-> effective-evidence tests
-> evidence tamper tests
-> CLI smoke
-> compileall and AST
-> Ruff and mypy when available
-> full repository pytest last in a complete checkout
```

Required cases:

- network default deny and read-only root;
- secret environment rejection;
- traversal and direct/parent symlink rejection;
- read-write model mount rejection;
- untrusted `NONE` rejection;
- missing resource limits;
- unauthorized GPU and unsupported Bubblewrap GPU rejection;
- command-injection text retained as one literal argv item;
- requested/effective mismatch and incomplete evidence;
- fake-child success, nonzero, timeout and oversized output;
- manifest/content tamper rejection;
- duplicate and extra evidence inventory rejection;
- explicit test-only acknowledgment for direct fixture execution.

Target-host Bubblewrap, OCI, cgroup, seccomp, AppArmor/SELinux and GPU isolation tests are deferred.
