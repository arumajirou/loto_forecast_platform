# TiRex-2 Changelog

## Unreleased — Contract v2 foundation

- added exact package and model provenance constants;
- added strict Request/Response v2 contracts;
- added arbitrary GameGeometry and target counts;
- added horizon 1/2/5 support without first-horizon truncation;
- added complete q0.1-q0.9 retention and validation;
- added fail-closed covariate chronology contract;
- added schema-v1 Loto7 compatibility conversion;
- added trusted snapshot hash checks;
- added isolated provider with fail-signaling exit codes and two-process certification CLI;
- added focused hermetic tests and documentation evidence.

Real TiRex-2 import, snapshot load, CPU/GPU inference, external GPU PID matching, full pytest,
Ruff, mypy, and GitHub Actions remain unverified.

## Unreleased — Reviewed lock workflow

- added a non-destructive isolated `uv lock` candidate generator;
- added deterministic package, dependency-edge, source, and artifact-hash review;
- bound the official TiRex-2 0.1.1 wheel/sdist SHA-256 values into policy;
- added dry-run and explicit-token reviewed-lock installation;
- added installed lock/report/approval cross-hash preflight;
- gated provider model import on successful reviewed-lock validation;
