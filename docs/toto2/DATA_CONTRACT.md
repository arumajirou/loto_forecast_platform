# Data contract

Each history row contains exactly the declared position columns. No missing or additional columns
are accepted. Every value must be finite. The request contains observed history only; future actuals
are not part of this schema.

Game domains:

| Game | Positions | Domain | Increasing |
|---|---:|---:|---|
| Numbers3 | 3 | 0..9 | no |
| Numbers4 | 4 | 0..9 | no |
| MiniLoto | 5 | 1..31 | yes |
| Loto6 | 6 | 1..43 | yes |
| Loto7 | 7 | 1..37 | yes |
