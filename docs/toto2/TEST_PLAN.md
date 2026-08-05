# Test plan

P0-P2 focused checks cover:

- all five game geometries;
- unknown-field and revision-drift rejection;
- draw-sequence chronology;
- univariate layout constraints;
- exact native tensor shape and all nine quantiles;
- q0.5 point parity;
- non-finite and quantile-crossing rejection;
- CUDA fallback rejection;
- snapshot hash and size validation;
- historical blocker supersession semantics;
- Python compilation, line length, structured-file parsing, and secret-pattern scan.

Real package import, snapshot load, inference, GPU PID/UUID/VRAM, separate-process repeatability,
OOF, Holdout, Prospective, and accuracy metrics remain later gates.
