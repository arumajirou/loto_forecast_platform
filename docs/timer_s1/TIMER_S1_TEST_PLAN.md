# Timer-S1 test plan

Focused tests cover strict field rejection, canonical identity, formal horizons, unsupported
covariates and multivariate settings, five-game position counts, chronology, mapping hashes,
future-actual and non-finite rejection, exact quantile inventory, q0.5 point identity, crossing
rejection, exact response matrix shapes, game-geometry binding, CPU/GPU evidence consistency,
safe artifact paths, and verified-only success statuses.

Provenance tests cover formal manifest completeness, safe manifest paths, config/index/weight-set
hash binding, request mismatch rejection, exact snapshot inventory, complete file size and hash
verification, remote-code allowlisting, timezone-aware review evidence, symlink rejection, and
same-size artifact tamper rejection. Provider tests retain structured pending behavior and verify
that invalid CLI run IDs are sanitized before failure serialization.

PR-B adds real dependency lock review, package import, immutable snapshot acquisition, CPU
inference, GPU inference, separate-process replay, PID/UUID/VRAM evidence, post-process release,
and save/reload tests. OOF, Holdout, and Prospective tests remain closed until runtime certification
passes.
