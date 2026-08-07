# P11 verification report

Status: `PARTIALLY_VERIFIED / LOCAL_PERSISTENCE_GPU_CONTRACT_VERIFIED`.

Local checks:

- six persistence families retained;
- process-boundary save/load evidence;
- artifact size and SHA-256 integrity;
- model identity and prediction replay;
- clean-save state removal;
- manual Torch companion checkpoint;
- best and last checkpoint restore;
- weights and encoder restore;
- CPU and CUDA map-location certification;
- GPU PID, VRAM, CUDA memory, and CPU fallback rejection;
- failure-retaining matrix;
- focused pytest: 13 passed;
- compileall, AST, YAML/JSON, and line-length checks: PASS.

Real Darts save/load, checkpoint, weights, cross-device, GPU PID, and VRAM execution
remain pending.
