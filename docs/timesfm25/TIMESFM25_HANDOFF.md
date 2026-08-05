# TimesFM 2.5 Handoff

Next implementation order:

1. Generate and commit isolated `uv.lock` files in the target CUDA environment.
2. Download and verify pinned PyTorch/Transformers snapshots.
3. Execute native GPU certification and separate-process reload.
4. Implement Transformers runner and parity checks.
5. Add XReg and LoRA in separate PRs.
6. Integrate shared worker/catalog only after the contract stabilizes.
