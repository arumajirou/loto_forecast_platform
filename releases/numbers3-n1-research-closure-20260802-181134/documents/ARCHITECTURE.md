# ARCHITECTURE

```text
Immutable raw data -> validation -> past-only features
 -> train-only transform/model -> temporal evaluation
 -> prediction lock (SHA-256) -> prospective registry
```
