# TimesFM 2.5 Evidence Review Policy

Status: `IMPLEMENTED / NOT_APPLIED_TO_REAL_GPU_EVIDENCE`.

## Purpose

P10 reviews the immutable ZIP and `.zip.sha256` produced by the P9 target-host
operator. It does not modify the source archive and does not infer GPU success from
model availability, configuration, or partial execution signals.

## Required verification layers

1. Verify the external archive SHA-256 sidecar.
2. Inspect every ZIP member before extraction.
3. Reject absolute paths, `..`, empty path components, backslashes, duplicates,
   encrypted members, symlinks, excessive member counts, oversized members, and
   suspicious compression ratios.
4. Require exactly one safe top-level Run ID.
5. Extract through explicit streamed copies into a new immutable review directory.
6. Verify the runtime bundle's existing `SHA256SUMS`.
7. Cross-check Run ID, backend, repository ID, revision, requested device,
   snapshot path, preflight status, runtime status, and provider response.
8. Require clean Git metadata, locked/offline provider command evidence, matching
   provider exit code, and non-empty NVIDIA process samples for strict GPU promotion.
9. Seal the review result with an outer `REVIEW_SHA256SUMS`.

## Formal promotion rules

`FORMAL_GPU_CERTIFIED` requires all of the following:

```text
runtime_status=VERIFIED_GPU
gpu_certification_status=PASS
provider_exit_code=0
timed_out=false
provider_response_valid=true
device_requested=cuda
model_parameter_device=cuda*
mean_output_device=cuda*
quantile_output_device=cuda*
external_pid_match=true
vram_peak_bytes>0
cpu_fallback=false
preflight.status=PASS
internal SHA256SUMS=PASS
```

`PARTIALLY_VERIFIED_GPU` is never promoted to formal GPU certification. Native
TimesFM CPU NumPy outputs therefore remain partial until real CUDA output-device
evidence exists.

`FORMAL_CPU_CERTIFIED` requires `runtime_status=VERIFIED_CPU`, a CPU request,
successful provider exit, no CPU-fallback classification, passing preflight, and
valid internal and external hashes.

Any mismatch, dirty Git worktree, failed runtime, unsafe archive, invalid sidecar,
missing NVIDIA samples, or missing evidence is `REJECTED`.

SHA-256 proves byte integrity after sealing; it is not a digital signature and does
not by itself prove who produced the archive.

## Immutability

The review directory name is `<run_id>-<archive_sha256_prefix>`. Existing review
directories are never overwritten. Review JSON, Markdown, archive digest metadata,
the extracted original bundle, and `REVIEW_SHA256SUMS` are preserved together.
