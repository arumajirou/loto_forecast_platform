"""Immutable payout/popularity data-plane contracts.

This package is intentionally separate from :mod:`loto.data.parser`, which parses draw outcomes.
Winner counts, prize amounts and sales must not become draw-prediction features accidentally.
"""

from loto.data.payouts.contracts import PayoutFact, RawPayoutSnapshot
from loto.data.payouts.parser import PayoutColumnMap, normalize_payout_dataframe
from loto.data.payouts.snapshot import materialize_raw_payout_snapshot
from loto.data.payouts.storage import write_payout_facts

__all__ = [
    "PayoutColumnMap",
    "PayoutFact",
    "RawPayoutSnapshot",
    "materialize_raw_payout_snapshot",
    "normalize_payout_dataframe",
    "write_payout_facts",
]
