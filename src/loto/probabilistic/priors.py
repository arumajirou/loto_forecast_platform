from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriorProfile:
    profile_id: str = "symmetric-dirichlet-v1"
    concentration: float = 1.0
    notes: str = "Positive mass on every legal category."
