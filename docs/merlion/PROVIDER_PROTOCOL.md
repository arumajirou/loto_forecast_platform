# Merlion Provider Protocol

Schema: `merlion-provider-v1`

Operations:

- `identity`
- `discover`
- `train_save`
- `load_predict`
- `verify_artifact`

Unknown fields, unsafe request IDs, absolute paths, parent traversal, missing lifecycle
inputs, and untrusted model manifests fail closed. Provider output uses an atomic file
replacement. The root adapter applies a timeout and bounded stdout/stderr capture.

`load_predict` is allowed only when the exact trusted-local model manifest SHA-256 is
supplied and every listed file still matches its recorded size and SHA-256. The manifest also
binds package version and upstream revision and rejects unlisted files and symlinks.
The expected manifest hash is the caller-provided trust anchor; this is not a digital
signature or external authenticity service.
