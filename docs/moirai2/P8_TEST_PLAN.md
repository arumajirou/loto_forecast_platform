# P8 Test Plan

1. Parse strict `nvidia-smi` GPU and compute-process CSV output.
2. Reject malformed process rows and missing external CUDA PID observations.
3. Observe real torch module forward input and output devices through hooks.
4. Reject zero forward calls, missing device evidence, or device-family mismatch.
5. Require two different provider process IDs.
6. Compare point forecast and q0.1 through q0.9 by canonical SHA-256.
7. Reject any changed quantile, series identity, prediction index, model identity, or artifact hash.
8. Compare covariate identity and matrix hashes between reload runs.
9. Reject CPU fallback and inconsistent provider/GPU process IDs.
10. Require CUDA provider PID disappearance after process exit.
11. Require an explicit local snapshot path and an unused output directory.
12. Save request, responses, stdout, stderr, exit codes, monitor samples, manifest, and SHA-256 sums.
13. Run compileall, focused tests, line-length inspection, structured-file parsing, and secret scan.
14. Defer real Uni2TS, GPU, full pytest, and GitHub Actions certification to the target host.
