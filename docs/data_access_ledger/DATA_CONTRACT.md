# Data Contract

## DatasetSlice

Required evidence includes dataset ID and lowercase SHA-256, role, game and series identity,
inclusive
row range, observed-time range, UTC availability, UTC forecast origin, target/actual flags, and
explicit
source immutability. `contains_actuals=true` is legal only for ACTUALS. Fold ID and fold role
are paired;
optional draw ID binds actuals to a forecast identity.

## StateReference

State evidence contains state ID/kind/hash, producer event, fitted dataset hash/role/rows,
owning run,
explicit authorized reuse runs, optional HPO fold hash, and an actual-bearing flag. Consumers
must use
an exact copy of the state produced by an earlier event. The producer operation must match the state
kind and fitted dataset evidence must match a producer input slice.

## AccessEvent

Events have positive sequence numbers, UTC timestamps, operation/stage, slices/states, optional
output
state, unique parents, forecast origin/identity, OOF fold/seed, and operator assertion fields.
OOF events
must include fold and seed. Self-parent references and duplicate state/parent IDs are rejected
by the
contract.

## DataAccessLedger

The ledger stores schema version, run, UTC creation timestamp, ordered events, event count,
first/last
event timestamps, expected OOF seeds, and a SHA-256 calculated from canonical content excluding
only the
`ledger_sha256` field. Structural cross-event errors are represented as validator findings so
the CLI
can return a complete report instead of failing at the first duplicate or graph error.
