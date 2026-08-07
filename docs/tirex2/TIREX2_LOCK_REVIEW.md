# TiRex-2 reviewed lock workflow

## Status

`PARTIALLY_VERIFIED / P1_LOCK_REVIEW_IMPLEMENTED / REAL_UV_RESOLUTION_PENDING`

This phase adds a fail-closed boundary between the isolated dependency declaration and model
loading. The existence of `uv.lock` alone is not accepted as reviewed runtime evidence.

## Workflow

1. `generate_tirex2_lock_candidate.py` copies only `pyproject.toml` into a new candidate
   directory and invokes `uv lock` there.
2. `lock_review.py` parses the candidate with the standard library, inventories every package,
   dependency edge, source type, and artifact SHA-256, and writes a deterministic report.
3. A human reviewer performs a dry-run, supplies the exact candidate lock SHA-256, reviewer
   identity, and timezone-aware review time.
4. Installation requires the literal token `APPLY-REVIEWED-TIREX2-LOCK` and atomically installs
   the lock, review report, and approval record as a mutually bound set.
5. `preflight_tirex2_runtime_lane.py` recomputes the report and validates every cross-hash before
   model import or snapshot loading.

## Static review policy

The review fails closed when any of the following is present:

- Git, path, URL, editable, directory, or workspace package sources;
- a registry other than `https://pypi.org/simple`;
- a registry package without a syntactically valid SHA-256 artifact hash;
- a direct dependency version outside its declared constraint;
- a dependency edge whose package name is absent from the lock;
- a missing root virtual project entry;
- an unsupported direct requirement syntax or environment marker;
- a TiRex-2 0.1.1 lock entry that does not contain an official wheel or sdist SHA-256.

Multiple locked versions remain visible as warnings and are not silently collapsed.

## Official TiRex-2 package evidence

The policy pins the two artifact hashes published for `tirex-2==0.1.1`:

```text
wheel  1d9f0ead93662d4438371ef0bb3b6319dc4811ba9d17fe343c8fa8f456b1730b
sdist  bc82b6e0698b9828888cd6e5037717dba8e107320116725061824308e10fbeb2
```

Official source:

- https://pypi.org/project/tirex-2/0.1.1/
- https://pypi.org/pypi/tirex-2/0.1.1/json

The package metadata declares Python `>=3.11,<3.14` and dependencies including Torch
`>=2.8,<2.10`, NumPy `~=2.1.3`, Hugging Face Hub `~=0.32.0`, FlashRNN, xLSTM, Einops, and
PyYAML. The repository lane remains Python 3.12 and records its own direct pins or bounded
constraints; the resolved graph must still pass the lock review.

## Approval binding

`LOCK_REVIEW_APPROVAL.json` binds:

- runtime lane;
- reviewer and timezone-aware review time;
- `pyproject.toml` SHA-256;
- `uv.lock` SHA-256;
- canonical review-report SHA-256;
- deterministic package-inventory SHA-256;
- zero review violations.

Changing the project, lock, report, package inventory, reviewer record, or lane causes preflight
failure.

## Non-claims

This implementation does not claim that:

- a real lock has been resolved on the target host;
- the complete dependency graph has been approved by a human;
- package files have been downloaded and independently re-hashed;
- licenses or vulnerabilities for all transitives have been accepted;
- TiRex-2 has been imported, loaded, or executed through the reviewed lane;
- CPU, CUDA, reload, GPU PID, VRAM-release, OOF, Holdout, or Prospective gates have passed.
