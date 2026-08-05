# Verification report

## Overall status

`PARTIALLY_VERIFIED / LOCAL_CONTRACTS_AND_PACKAGE_VERIFIED / REAL_CAMPAIGN_BLOCKED`

## Passed

- P1-P12 contract implementation documented through Draft PR #47;
- 108 documented focused contract tests across increments;
- 10 final-package focused tests;
- final-package compileall and AST checks;
- package YAML parsing;
- 100-character source/test line gate;
- exact required-document membership and order;
- canonical SHA-256 generation and verification;
- deterministic ZIP output with fixed timestamps and normalized modes;
- ZIP CRC, extraction, and byte-for-byte source comparison;
- package tamper and stale-checksum rejection.

## Not claimed

- one combined 118-test repository run;
- Ruff, mypy, pytest-cov, or full repository pytest success;
- real Darts or cross-library package compatibility;
- real model fitting, inference, checkpoint, or persistence success;
- real CUDA use, GPU PID, VRAM, or CPU-fallback behavior;
- real wrapper parity;
- real OOF, Holdout, or Prospective improvement;
- a cross-library champion.

## CI boundary

At the P12 source commit, GitHub Actions run `30998803666` / #1746 ended before job steps were
created. Checkout and tests did not start, so it is classified `CI_BLOCKED_PRE_RUN`, not as a
code or test failure.
