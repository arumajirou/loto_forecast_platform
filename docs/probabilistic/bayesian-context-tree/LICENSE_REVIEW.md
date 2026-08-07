# License Review and Clean-Room Boundary

## Findings

The CRAN `BCT` package declares `GPL (>= 2)`. The historical standalone C++
repository did not provide a confirmed license during PR-A investigation.

## PR-A rule

No upstream R or C++ source, variable names, class structures, fixtures, or test
vectors are copied or translated. The project files in this PR contain only
independently authored contracts, configuration, documentation, and tests for
those contracts. Mathematical implementation is deferred.

## Future implementation rule

PR-B must be written from the published mathematical description and separately
created small-case calculations. Any proposal to vendor, translate, link, or
execute upstream GPL code requires a new explicit license review and must not be
silently included in the Python implementation.

## Status

- `UPSTREAM_CODE_COPIED=false`
- `DIRECT_CODE_REUSE=BLOCKED_LICENSE`
- `CLEAN_ROOM_CONTRACT_WORK=ALLOWED`
- Commercial eligibility of a future distributed implementation is not certified
  by PR-A.
