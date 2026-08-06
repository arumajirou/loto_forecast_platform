# Architecture

```text
fixed chronyc argv or retained text files
                 |
                 v
       ChronycAdapter / parser
                 |
                 v
        ClockObservation + raw hashes
                 |
                 v
      pure evaluate_clock_health()
                 |
                 v
        ClockHealthDecision
                 |
                 v
 atomic evidence bundle + verifier
```

## Modules

- `canonical.py`: duplicate-safe JSON, canonical JSON, SHA-256.
- `contracts.py`: strict immutable evidence and policy models.
- `evaluator.py`: pure fail-closed policy evaluation.
- `chronyc.py`: fixed-argv subprocess boundary, parser, raw verification.
- `io.py`: atomic writes, manifest/checksum creation, complete verification.
- `run_clock_health_check.py`: operator entry point and exit-code mapping.

The core contracts and evaluator have no subprocess dependency. Target-host I/O is injected or
isolated in the adapter. Existing Prediction Lock and Trusted Evidence packages remain unchanged.
