# P8 Runtime Certification

Status: `IMPLEMENTED / LOCAL_FAKE_BOUNDARY_VERIFIED / REAL_RUNTIME_PENDING`.

P8 launches the existing provider runner twice from the same immutable request and explicit local
snapshot. Each invocation is a new operating-system process with its own request, response, logs,
exit code, GPU monitor samples, and run evidence.

Formal certification requires:

- two distinct provider PIDs;
- identical model revision, config SHA-256, and weight SHA-256;
- exact SHA-256 equality of point forecast, all nine native quantiles, series identity, and horizon;
- identical covariate names, shapes, and matrix hashes;
- observed model forward input and output tensor devices;
- requested and effective devices to match with no CPU fallback;
- for CUDA, an external `nvidia-smi` sample matching the provider PID and one GPU UUID;
- positive provider peak VRAM and disappearance of the provider PID after exit.

The result directory is created with `exist_ok=false`. Failed and successful runs are immutable and
receive separate Run IDs. `provider.json` is not treated as model serialization. The certified
lifecycle is `BASE_SNAPSHOT_RELOADED` because both processes reload the same pinned base snapshot.

P8 does not open OOF, Holdout, Prospective, accuracy comparison, fine-tuning, shared catalog
registration, production promotion, or commercial deployment.
