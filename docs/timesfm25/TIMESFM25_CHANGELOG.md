# TimesFM 2.5 Changelog

## Unreleased

- Added provider contract v2 and strict Pydantic models.
- Added dynamic GameGeometry and arbitrary series counts.
- Added multi-horizon mean/median/nine-quantile preservation.
- Added backend/package/checkpoint manifests.
- Added GPU evidence and parity schemas.
- Added schema-v1 compatibility conversion.
- Added immutable runtime-certification evidence bundles and SHA-256 sealing.
- Added target-host preflight for isolated lock, exact dependency pins, snapshot SHA,
  CUDA availability, and offline execution.
- Added a schema-v2 runtime request example and explicit lock-generation command.
- Added a provider execution gate that blocks model loading after failed preflight.
- Added a target-host operator CLI for preflight, tmux launch, status inspection,
  deterministic ZIP finalization, and archive SHA-256 sidecars.
- Added fail-closed operator states for running, partial, failed, incomplete, and
  corrupt runtime bundles.
- Added focused tests and phased verification documentation.
