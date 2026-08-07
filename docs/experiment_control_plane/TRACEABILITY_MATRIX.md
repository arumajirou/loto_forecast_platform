# Traceability Matrix

| Requirement | Design | Verification |
|---|---|---|
| FR-001/002 Plan intake and validation | `DATA_CONTRACT.md`, Plan validator | contract/schema negative tests |
| FR-003 Deterministic hashes | `DETAILED_DESIGN.md` canonical identity | serialization/hash mutation tests |
| FR-004/005 Approval and role policy | `APPROVAL_MODEL.md` | approval expiry/revocation/self-approval tests |
| FR-006 Idempotent enqueue | command transaction algorithm | concurrency/idempotency tests |
| FR-007 Lease/fencing | lease section | takeover/stale-worker tests |
| FR-008 Heartbeat/cancel | agent loop/cancellation | crash, timeout, process-tree tests |
| FR-009 Evidence index | `EVIDENCE_INDEX_CONTRACT.md` | hash/URI/retention tests |
| FR-010 Result verification | ResultSummary and gate | corrupted/missing/subject mismatch tests |
| FR-011 GitHub projection | architecture/outbox | outage/replay/reconciliation tests |
| FR-012 Lane separation | detailed lane controls | GPU fallback and API cost tests |
| FR-013 Audit trail | append-only repository | tamper/reorder/deletion tests |
| FR-014 Export | CLI/export and manifest | deterministic export/SHA tests |
| FR-015 Promotion boundary | architecture ownership | no-auto-promotion integration test |
| NFR-001 strict models | basic design | Pydantic extra-field tests |
| NFR-002 canonicalization | detailed design | golden canonical bytes |
| NFR-003 tamper evidence | approval/audit design | chain verification tests |
| NFR-004 retry/timeout | service/agent design | fault injection |
| NFR-005 secret safety | evidence and lane controls | detect-secrets/custom pattern scan |
| NFR-006/007 observability | architecture | JSON log schema/trace propagation tests |
| NFR-008 atomic durability | repository/storage ports | DB/object-store failure injection |
| NFR-009 trusted time | ownership boundary | wrong/missing trusted-time rejection |
| NFR-010 operator resilience | `RUNBOOK.md` | terminal-close recovery drill |
| NFR-011 gate order | `TEST_PLAN.md` | verification report |
| NFR-012 Git safety | implementation prompt | branch/remote/diff/push audit |
