# Chronos-2 Requirements

## Scope

P0-P4 only: isolated runtime specification, strict request/response contract, arbitrary game geometry, horizons 1/2/5, quantile-preserving output, snapshot manifest, reference reload protocol, CPU mock tests, and GPU evidence schema.

## Acceptance criteria

1. Unknown request fields fail closed.
2. `local_files_only` is always true.
3. Model and package revisions are immutable identifiers.
4. Position count and names are derived from the request.
5. Numbers3, Numbers4, MiniLoto, Loto6, Loto7, and Bingo5 compile through one provider.
6. Predictions preserve series identity, horizon identity, point/median distinction, and every quantile.
7. Non-finite values, shape mismatches, chronological violations, and quantile crossing fail.
8. CPU preprocessing is not mislabeled as model CPU fallback.
9. A reference manifest is not called a saved model.
10. Holdout and Prospective remain unopened.
