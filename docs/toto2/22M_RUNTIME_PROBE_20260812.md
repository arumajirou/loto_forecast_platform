# Toto 2.0 22M runtime probe evidence — 2026-08-12

Status: `PARTIALLY_VERIFIED / SNAPSHOT_AND_REPLAY_VERIFIED / FORMAL_RUNTIME_BLOCKED`.

## Scope

This record preserves the reviewed results from GitHub Actions run `31584682671` on exact head
`5466669e1f1fa297b327ca89ae6acaba1cf6a431`. The uploaded artifact is
`toto2-22m-runtime-probe-31584682671-1`, artifact ID `9136641679`, with archive SHA-256
`d243b15ca0bee3aa7ae9fa8310c94a3a61027d87842ace72a18aeb28c9d3e503`.

The workflow completed successfully, but the certification payload is intentionally
`PARTIAL_PASS`; workflow success is not treated as formal runtime certification.

## Pinned upstream snapshot

- repository: `Datadog/Toto-2.0-22m`
- revision: `3affccf372ff82f5d200ac76fad3dbcdeb64299a`
- `.gitattributes`: SHA-256 `11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361`, 1,519 bytes
- `README.md`: SHA-256 `ec40d6b5978fe1ed22e92abe5f9033b5147fc474209dc245df3b4fb8d4dfbf4c`, 352 bytes
- `config.json`: SHA-256 `abeaf0fcd54aaac66757fde69ec3ddb4d3bfdcf96e0c8f767aefd03ab4c9e8d9`, 593 bytes
- `model.safetensors`: SHA-256 `9cd503d82df3aa71747862688f47a31c1d0a4b80f898df6e046189016eaa21dd`, 87,669,368 bytes

The online and offline-local replay processes observed the same four-file inventory and hashes.

## Runtime identity

- Python: `3.12.13`
- Torch: `2.13.0+cu130`
- Torch CUDA runtime: `13.0`
- `toto-2`: `2.0.0`
- `toto-models`: `1.0.0`
- model class: `Toto2Model`
- exact parameter count: `21,915,584`
- patch size: `32`
- native quantiles: q0.1 through q0.9

## CUDA and replay evidence

- GPU: NVIDIA GeForce RTX 5070 Ti
- GPU UUID: `GPU-fac07577-072e-c021-9ac4-d7dc9b9711af`
- input shape: `[1, 3, 128]`
- output shape: `[9, 1, 3, 1]`
- output finite: yes
- quantile monotonicity: yes
- CPU fallback: no
- PyTorch peak VRAM: `150,128,128` bytes in each process
- provider process IDs: `811063`, `811252`
- both provider processes exited: yes
- exact native output SHA-256 in both processes: `2cd27d69c840f3dec42f3846c553e98ec1d67b37d794775f8c0942798279e38d`
- exact `numpy.array_equal` replay: yes

## Remaining blocker

The runner kernel is WSL2. NVIDIA documents that NVML / `nvidia-smi` has a limited feature set on
WSL and does not support the active compute process query required by the existing formal Toto
certification contract. Therefore the exact external provider PID could not be observed through
`nvidia-smi`, and external post-exit GPU release cannot be certified on this host.

Blocker: `WSL_NVML_ACTIVE_COMPUTE_PROCESS_QUERY_UNSUPPORTED`.

Consequences:

- complete snapshot byte identity: `VERIFIED`
- exact model parameter count: `VERIFIED`
- CUDA model load/inference smoke: `VERIFIED`
- two-process exact replay: `VERIFIED`
- provider processes exited: `VERIFIED`
- external GPU PID evidence: `BLOCKED`
- external post-exit GPU release evidence: `BLOCKED`
- formal runtime certification: `BLOCKED`
- shared routing: `FORBIDDEN`
- OOF: `NOT_RUN`
- Holdout: `CLOSED`
- Prospective: `CLOSED`
- accuracy or superiority claim: `FORBIDDEN`
