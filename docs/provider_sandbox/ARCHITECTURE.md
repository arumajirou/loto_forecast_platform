# Architecture

```text
policy.json ─┐
request.json ├─> pure validation ─> argv builder ─> SandboxArgvPlan
backend.json ┘

requested policy + effective observation
                    └─> effective verifier ─> VERIFIED/MISMATCH/INCOMPLETE

validated plan ─> bounded child runner ─> hashed SandboxProcessResult

all strict objects ─> atomic evidence writer ─> manifest + SHA256SUMS
                                              └─> offline verifier
```

## Boundaries

- `contracts.py`: strict schemas and self-hash validation.
- `validation.py`: pure request, path and effective-evidence validation.
- `argv.py`: deterministic backend-specific argument construction.
- `executor.py`: the only source module importing `subprocess`.
- `evidence.py`: atomic persistence and complete offline revalidation.
- `scripts/run_provider_sandbox.py`: operator-facing validation and test-fixture entrypoint.

The core imports no provider implementation and no Runtime Certification module. A later adapter may
compose both systems without changing either authority boundary.
