# Data Contract

Each position is an independent univariate series. Batched layout uses the batch dimension
only and does not imply cross-position learning. Position counts are 3, 4, 5, 6, and 7 for
Numbers3, Numbers4, MiniLoto, Loto6, and Loto7.

Draw-sequence evidence must be unique, strictly increasing, gap-free, cutoff-bounded, and
hashed canonically. Calendar-time evidence is validated against the official weekday schedule;
holiday and year-end exceptions require a reviewed override and otherwise fail closed.
Timestamps are audit evidence only and are not passed as Timer covariates.
