# Migration Notes

This PR is adoption-neutral and add-only. No existing pipeline is rewired.

A later adapter must:

1. map one bounded workflow to `RunCommand` without changing lifecycle semantics;
2. emit opaque evidence references instead of copying owner schemas;
3. persist event and idempotency records in one database transaction;
4. enforce a unique idempotency key and revision compare-and-swap;
5. persist monotonically increasing fencing tokens;
6. replay historical events and compare reconstructed state before enabling writes;
7. keep old execution authoritative until parity tests pass;
8. add rollback that disables the adapter without rewriting old evidence.

No bulk migration or silent status conversion is permitted.
