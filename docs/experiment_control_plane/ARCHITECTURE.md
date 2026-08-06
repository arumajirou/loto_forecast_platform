# Architecture

## 1. Three-plane architecture

```text
+---------------- GitHub Control Plane ----------------+
| Issue Forms | Plan PR | Reviews | Checks | Projects |
| Rulesets    | Dispatch intent | Result PR | Release |
+-------------------------+----------------------------+
                          |
                          | short authenticated commands
                          v
+--------------- Execution Plane ----------------------+
| Local Experiment Agent                               |
| CPU lane | GPU lane | Proprietary API lane           |
| clean workspace | lease | heartbeat | cancel | retry |
+-------------------------+----------------------------+
                          |
                          | immutable artifacts and records
                          v
+--------------- Evidence Plane -----------------------+
| PostgreSQL | MLflow | Parquet | Object Storage       |
| Logs/Loki | Traces/Tempo | Metrics/Prometheus        |
+-------------------------+----------------------------+
                          |
                          | hashes and safe references
                          v
                  GitHub Evidence Index
```

## 2. Trust boundaries

- GitHub input is untrusted until schema, identity, authorization, and branch checks pass.
- The Local Agent does not trust Project fields or labels as authorization.
- Proprietary API secrets never enter the local model lane.
- GitHub receives no raw secret, large model output, or credential-bearing URI.
- External evidence is accepted only after hash and inventory verification.

## 3. Durability

The agent and queue later integrate with PR #140's durable lifecycle and outbox. GitHub Actions is
not the durable workflow engine.

## 4. Observability

The agent emits the common telemetry owned by PR #141. GitHub receives low-frequency status
projections, not high-cardinality telemetry.

## 5. Failure model

- GitHub unavailable: local execution may continue from durable state; projection is reconciled.
- Local host unavailable: lease expires; the run becomes blocked or resumes with a new fencing token.
- Evidence store unavailable: no completion claim; outbox retries and reconciliation are required.
- Actions unavailable: manual audited enqueue fallback may be used only after explicit approval.
