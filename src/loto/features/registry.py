from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from loto.features.hash import stable_hash
from loto.features.spec import Availability, FeatureSpec


@dataclass
class FeatureRegistry:
    _items: dict[str, FeatureSpec] = field(default_factory=dict)

    def register(self, spec: FeatureSpec, *, replace: bool = False) -> None:
        if spec.name in self._items and not replace:
            raise ValueError(f"feature already registered: {spec.name}")
        self._items[spec.name] = spec

    def get(self, name: str) -> FeatureSpec:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"unknown feature: {name}") from exc

    def names(self, availability: Availability | None = None) -> tuple[str, ...]:
        values = self._items.values()
        if availability is not None:
            values = (item for item in values if item.availability == availability)
        return tuple(sorted(item.name for item in values))

    def validate_frame(self, frame: pd.DataFrame, *, allow_unknown: bool = False) -> None:
        unknown = sorted(set(frame.columns) - set(self._items))
        if unknown and not allow_unknown:
            raise ValueError(f"unregistered feature columns: {unknown}")
        missing = sorted(
            item.name for item in self._items.values() if item.required and item.name not in frame
        )
        if missing:
            raise ValueError(f"missing required feature columns: {missing}")
        forbidden = sorted(
            item.name
            for item in self._items.values()
            if item.availability == Availability.FORBIDDEN and item.name in frame
        )
        if forbidden:
            raise ValueError(f"forbidden feature columns present: {forbidden}")

    def manifest(self) -> dict[str, object]:
        specs = [self._items[name].to_dict() for name in sorted(self._items)]
        return {"schema_version": "1.0", "features": specs, "feature_set_hash": stable_hash(specs)}
