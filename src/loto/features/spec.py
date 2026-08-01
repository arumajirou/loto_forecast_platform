from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Availability(StrEnum):
    HISTORICAL = "historical"
    FUTURE_KNOWN = "future_known"
    STATIC = "static"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    dtype: str
    availability: Availability
    source: str
    description: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "availability": self.availability.value,
            "source": self.source,
            "description": self.description,
            "required": self.required,
        }
