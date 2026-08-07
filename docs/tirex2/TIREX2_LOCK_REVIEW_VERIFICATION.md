# TiRex-2 lock review verification

## Status

`PARTIALLY_VERIFIED / LOCAL_PURE_TESTS_PASS / TARGET_HOST_PENDING`

## Executed

- focused TiRex-2 tests: `47 passed`;
- Python `compileall`: `PASS`;
- Python line-length scan at 100 characters: `PASS`;
- non-destructive candidate generation through a fake `uv` process boundary: `PASS`;
- candidate artifact manifest and SHA-256 generation: `PASS`;
- dry-run installation leaves the runtime lane unchanged: `PASS`;
- explicit approval token and exact candidate lock SHA-256: `PASS`;
- lock/report/approval installation and preflight cross-hash validation: `PASS`;
- post-install lock tampering causes non-zero preflight: `PASS`;
- phase-delta artifact manifest and SHA-256 inventory: `PASS`;
- Ruff: `UNAVAILABLE`;
- mypy: `UNAVAILABLE`.

The fake `uv` process wrote a deterministic synthetic lock only to exercise orchestration and
error boundaries. It is not real dependency resolution or package verification.

## Focused rejection coverage

- VCS source;
- missing registry artifact hash;
- incompatible direct dependency version;
- unrecognized TiRex-2 artifact hash;
- naive review timestamp without timezone;
- wrong apply token;
- installed lock tampering.

## Pending target-host gate

1. Run the candidate generator with the real `uv` executable.
2. Retain stdout, stderr, exit code, candidate status, manifest, and SHA-256 sums.
3. Inspect every package source, version, dependency edge, artifact hash, license, and warning.
4. Dry-run installation with the exact lock SHA-256.
5. Apply only after explicit human approval.
6. Run preflight before `uv run --frozen` and before provider startup.
7. Execute a real package import and CPU smoke.
8. Execute the CUDA and two-process reload certification matrices.
