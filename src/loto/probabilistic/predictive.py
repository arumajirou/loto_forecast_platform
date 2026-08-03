from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from loto.game.geometry import GameGeometry
from loto.probabilistic.contracts import PredictiveDistribution


def summarize_draws(
    draws: np.ndarray,
    *,
    model_id: str,
    game: str,
    target_mode: str,
    draw_id: str,
    geometry: GameGeometry,
    protocol_hash: str,
    execution_fingerprint: str,
) -> tuple[np.ndarray, pd.DataFrame]:
    draws = np.asarray(draws, dtype=float)
    mean = draws.mean(axis=0)
    sd = draws.std(axis=0, ddof=1) if draws.shape[0] > 1 else np.zeros_like(mean)
    low = np.quantile(draws, 0.025, axis=0)
    high = np.quantile(draws, 0.975, axis=0)
    rows: list[dict[str, Any]] = []
    for position in range(mean.shape[0]):
        for candidate in range(mean.shape[1]):
            record = PredictiveDistribution(
                model_id=model_id,
                game=game,
                target_mode=target_mode,
                draw_id=str(draw_id),
                position=position + 1 if mean.shape[0] > 1 else None,
                candidate=candidate + geometry.value_min,
                probability_mean=float(mean[position, candidate]),
                probability_sd=float(sd[position, candidate]),
                hdi_low=float(np.clip(low[position, candidate], 0.0, 1.0)),
                hdi_high=float(np.clip(high[position, candidate], 0.0, 1.0)),
                posterior_draw_count=int(draws.shape[0]),
                protocol_hash=protocol_hash,
                execution_fingerprint=execution_fingerprint,
            )
            rows.append(record.model_dump())
    return mean, pd.DataFrame(rows)
