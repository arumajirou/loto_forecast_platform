from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from loto.features.hash import frame_hash, protocol_hash
from loto.features.registry import FeatureRegistry
from loto.features.spec import Availability


@dataclass(frozen=True)
class ForecastInput:
    history: pd.DataFrame
    historical_exogenous: pd.DataFrame | None
    future_exogenous: pd.DataFrame | None
    static_exogenous: pd.DataFrame | None
    feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    cutoff_draw: int | None
    cutoff_time: pd.Timestamp | None
    feature_set_hash: str
    source_data_hash: str

    @classmethod
    def build(
        cls,
        *,
        history: pd.DataFrame,
        registry: FeatureRegistry,
        target_columns: tuple[str, ...],
        historical_exogenous: pd.DataFrame | None = None,
        future_exogenous: pd.DataFrame | None = None,
        static_exogenous: pd.DataFrame | None = None,
        cutoff_draw: int | None = None,
        cutoff_time: pd.Timestamp | None = None,
    ) -> ForecastInput:
        targets = set(target_columns)
        forbidden = targets & set(registry.names())
        if forbidden:
            raise ValueError(f"target columns registered as features: {sorted(forbidden)}")
        feature_columns = tuple(
            name
            for name in registry.names()
            if registry.get(name).availability != Availability.FORBIDDEN
        )
        manifest = registry.manifest()
        return cls(
            history=history.copy(),
            historical_exogenous=None
            if historical_exogenous is None
            else historical_exogenous.copy(),
            future_exogenous=None if future_exogenous is None else future_exogenous.copy(),
            static_exogenous=None if static_exogenous is None else static_exogenous.copy(),
            feature_columns=feature_columns,
            target_columns=target_columns,
            cutoff_draw=cutoff_draw,
            cutoff_time=cutoff_time,
            feature_set_hash=str(manifest["feature_set_hash"]),
            source_data_hash=frame_hash(history),
        )

    def manifest(self) -> dict[str, object]:
        return {
            "feature_columns": list(self.feature_columns),
            "target_columns": list(self.target_columns),
            "cutoff_draw": self.cutoff_draw,
            "cutoff_time": None if self.cutoff_time is None else self.cutoff_time.isoformat(),
            "feature_set_hash": self.feature_set_hash,
            "source_data_hash": self.source_data_hash,
            "protocol_hash": protocol_hash(
                feature_manifest={"feature_columns": self.feature_columns},
                cutoff={"draw": self.cutoff_draw, "time": self.cutoff_time},
                transforms=["point_in_time"],
            ),
        }
