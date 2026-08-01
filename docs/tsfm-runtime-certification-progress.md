# TSFM Runtime Certification Progress

Updated: 2026-08-01

## Current Status

- Total models: 21
- Runtime certified: 8
- Remaining: 13
- Progress: 38.1%
- Current branch: feat/chronos-2-runtime-audit-v1
- Next model: chronos-t5-base

## Certified

### chronos-2

- Branch: feat/chronos-2-runtime-audit-v1
- Commit: pending
- Push: pending
- repo_id: amazon/chronos-2
- revision: 29ec3766d36d6f73f0696f85560a422f50e8498c
- runner: scripts/run_chronos_2_provider.py
- provider: src/loto/models/providers/chronos.py
- GPU: cuda:0
- CPU fallback: false
- CPU preprocessing: true
- peak VRAM: 497113088
- external PID captures: 11
- GPU PID: 919682
- weight SHA-256: ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42
- config SHA-256: ef1143bfdc9c0376d9a056eefca46cb4b1ec3d0ffacd541ff56feb40fb708031
- license: Apache-2.0, APPROVED
- dedicated test: tests/test_chronos_2_runtime_audit.py
- hash verification: audit/tsfm-runtime/chronos-2/sha256sum.txt OK

## Remaining Ledger Order

1. chronos-t5-base
2. granite-flowstate-r1
3. kronos-base
4. lag-llama
5. moirai-1.0-base
6. moirai-2.0-small
7. moment-1-large
8. moment-1-small
9. sundial-base
10. t0-alpha
11. timesfm-2.5-transformers
12. toto-2.0-4m
13. toto-open-base

## Blocked

None recorded.
