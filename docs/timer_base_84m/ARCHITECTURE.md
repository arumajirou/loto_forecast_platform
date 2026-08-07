# Architecture

The root process communicates with an isolated Python 3.10 provider process through JSON.
PR-A implements only identity, request validation, environment validation, snapshot-manifest
validation, property inspection, and close. Load and predict raise dedicated pending statuses.

The official source repository head is retained as provenance, while the HF model revision
controls the executable snapshot. These identities are not claimed to be byte-equivalent.
Remote code may execute only after revision, exact allowlist, every file SHA-256, and explicit
review approval all agree.
