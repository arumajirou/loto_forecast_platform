# Runtime Certification SDK Provider Migration Checklist

Migrate one provider per PR after this foundation is merged.

## Before implementation

- [ ] Re-fetch current main and the provider PR stack.
- [ ] Identify the authoritative provider-specific runtime contract.
- [ ] Freeze package, model, revision and snapshot identities.
- [ ] List provider semantics that must remain outside the SDK.
- [ ] Record current status names and evidence file layout.
- [ ] Confirm no Holdout, Prospective or accuracy behavior is in scope.

## Adapter implementation

- [ ] Import the common SDK from provider-owned adapter code; never import provider code into the SDK.
- [ ] Convert the native request to `RequestIdentity` and retain canonical request bytes.
- [ ] Convert package and model provenance to common identity records.
- [ ] Convert snapshot files to `ArtifactIdentity` records.
- [ ] Construct provider commands without shell interpolation.
- [ ] Decode provider responses into `RunObservation`.
- [ ] Bind REAL device samples to the executor-owned process-instance SHA-256, not PID alone.
- [ ] Preserve model-specific load, input, inference and semantic checks.
- [ ] Map real/synthetic/fake origin explicitly.
- [ ] Keep CPU_SMOKE and GPU_FORMAL as separate profiles.
- [ ] Keep accuracy status separate and initially `NOT_EVALUATED`.

## Parity evidence

- [ ] Run legacy and common verifier over the same synthetic fixture.
- [ ] Compare request, package, model, artifact and output hashes.
- [ ] Compare timeout and non-zero-exit handling.
- [ ] Compare shape, finite and quantile checks.
- [ ] Compare requested/effective device and CPU-fallback handling.
- [ ] Compare GPU PID, UUID, VRAM and PID-release checks.
- [ ] Compare PID-reuse resistance and external-sample time/process binding.
- [ ] Compare save/reload/re-predict and replay tolerance.
- [ ] Compare manifest, SHA256SUMS and evidence ZIP bytes or documented format differences.
- [ ] Prove synthetic evidence remains PARTIALLY_VERIFIED.

## Real target-host gate

- [ ] Execute CPU smoke with a real provider.
- [ ] Execute GPU formal only when supported and retain external evidence.
- [ ] Verify two distinct real processes.
- [ ] Verify source and artifact immutability.
- [ ] Independently review the evidence ZIP.
- [ ] Do not claim accuracy, OOF, Holdout, Prospective or promotion.

## Removal gate

- [ ] Keep provider-local implementation until parity and real runtime evidence pass.
- [ ] Remove only duplicated common code, not provider semantics.
- [ ] Preserve old evidence readers or provide an explicit versioned migration.
- [ ] Run focused tests, Ruff, mypy and final full pytest when available.
- [ ] Keep the migration PR Draft until substantive review and actionable CI pass.
