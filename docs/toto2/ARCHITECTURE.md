# Architecture

```text
request JSON
  -> strict Pydantic contract
  -> isolated Toto runtime (future P3)
  -> native tensor [Q=9,B=1,S,H]
  -> dependency-light response adapter
  -> shape / finite / monotonicity / device checks
  -> response JSON with q0.1..q0.9 and q0.5 point forecast
```

The root environment can execute contract and adapter tests without importing Toto packages. The
Python 3.12 environment declaration is intentionally lockless until a target-host dependency review
produces an approved `uv.lock`.
