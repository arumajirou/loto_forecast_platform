# MLForecast final evidence archive

## Purpose

The final evidence archive packages one completed final-verification Run into a deterministic ZIP. A recipient can verify the ZIP without extracting untrusted archive paths first.

This layer preserves the source Run status. `FINAL_EVIDENCE_VERIFIED` proves archive safety, transport integrity, source-manifest consistency, and successful independent verification of the embedded source handoff and runtime evidence. It does not convert `FAILED`, `BLOCKED`, or `PARTIAL` into success.

## Formal entrypoint

```bash
bash docs/mlforecast/run_final_verification_portable.sh
```

The wrapper runs the complete final gate, creates the final evidence ZIP, and independently verifies it. Formal end-to-end success requires:

```text
FINAL_EVIDENCE_CERTIFIED
```

with exit status 0.

A blocked or failed source Run is still packaged when the evidence is internally valid. The wrapper prints `FINAL_EVIDENCE_PRESERVED` and returns the original nonzero source status.

## Outputs

```text
artifacts/mlforecast-final-evidence/
  <FINAL_RUN_ID>.final-evidence.zip
  <FINAL_RUN_ID>.final-evidence.zip.sha256
  <FINAL_RUN_ID>.final-evidence.verification.json
```

## Independent verification

```bash
uv run --frozen -- \
  python -m loto.mlforecast.final_evidence \
  --verify \
  --zip /absolute/path/<FINAL_RUN_ID>.final-evidence.zip \
  --sha256 /absolute/path/<FINAL_RUN_ID>.final-evidence.zip.sha256 \
  --report /absolute/path/<FINAL_RUN_ID>.final-evidence.verification.json
```

Formal archive-integrity success is `FINAL_EVIDENCE_VERIFIED`.

## Verification gates

The verifier rejects malformed sidecars, digest mismatch, CRC failures, unsafe paths, symlink/device/encrypted members, duplicate or unsorted members, nondeterministic timestamps, excessive archive size, unexpected source files, manifest or checksum disagreement, final-report status disagreement, missing final-gate evidence, incomplete source handoff, and invalid runtime evidence.

The embedded handoff ZIP and runtime ZIP are written only to a temporary private directory using fixed known filenames and are then passed to their existing independent verifiers. No archive member path is extracted directly.
