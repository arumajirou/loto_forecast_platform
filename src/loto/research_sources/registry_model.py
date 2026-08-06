from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, model_validator

from .common import STRICT_CONFIG
from .records import ResearchSourceRecord

class ResearchSourceRegistry(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: Literal["1.0.0"]
    generated_at: AwareDatetime
    records: tuple[ResearchSourceRecord, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> ResearchSourceRegistry:
        source_ids = [record.source_id for record in self.records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source_id")
        model_ids = [record.logical_model_id for record in self.records]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("duplicate logical model_id")

        records_by_id = {record.source_id: record for record in self.records}
        for record in self.records:
            target = record.superseded_by_source_id
            if target is not None and target not in records_by_id:
                raise ValueError(f"unknown superseded target: {target}")

        for start in source_ids:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise ValueError("superseded revision cycle detected")
                seen.add(current)
                current = records_by_id[current].superseded_by_source_id
        return self

