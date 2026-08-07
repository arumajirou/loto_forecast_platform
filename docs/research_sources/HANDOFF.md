# Handoff

## Current state

```text
SOURCE_REGISTRY_CONTRACT_IMPLEMENTED
INITIAL_RECORDS_VALIDATED
MODEL_IMPLEMENTATION_NOT_STARTED
RUNTIME_NOT_EXECUTED
PRODUCTION_REGISTRATION_NOT_PERFORMED
```

## Next model intake PR

1. Select exactly one logical model ID.
2. Re-fetch official paper, source repository, model repository, releases, security notices, and
   license files.
3. Resolve source and model revisions to immutable commits.
4. Download only the pinned snapshot in the later authorized runtime PR.
5. Record exact required file paths, byte sizes, and SHA-256 values.
6. Review package, Python, Torch, Transformers, CUDA, and platform compatibility.
7. Review code and weight licenses separately.
8. If remote code is required, bind human review to exact file hashes and an allowlist.
9. Update the source record in an isolated PR before provider implementation.
10. Keep Runtime Certification, OOF, Holdout, Prospective, Registry, and Promotion as separate gates.

## Rollback

The implementation is add-only. Before merge, close the Draft PR. After merge, revert the PR.
There is no database, package, model, artifact, data, or production state to roll back.
