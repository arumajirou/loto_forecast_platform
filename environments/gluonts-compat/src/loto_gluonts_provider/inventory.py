from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class InventoryCategory(StrEnum):
    PYTORCH_ESTIMATOR = "PYTORCH_ESTIMATOR"
    NATIVE_PREDICTOR = "NATIVE_PREDICTOR"
    EXTENSION = "EXTENSION"
    DISTRIBUTION_OUTPUT = "DISTRIBUTION_OUTPUT"


class CheckState(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FormalAvailability(StrEnum):
    DISCOVERED_ONLY = "DISCOVERED_ONLY"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class RuntimeInventoryEntry(BaseModel):
    """One runtime candidate with independently tracked certification stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    category: InventoryCategory
    module: str = Field(min_length=1)
    qualname: str | None = None
    class_path: str | None = None
    expected: bool = True
    import_state: CheckState = CheckState.NOT_RUN
    export_state: CheckState = CheckState.NOT_RUN
    class_state: CheckState = CheckState.NOT_RUN
    signature_state: CheckState = CheckState.NOT_RUN
    constructor_state: CheckState = CheckState.NOT_RUN
    fit_state: CheckState = CheckState.NOT_RUN
    predict_state: CheckState = CheckState.NOT_RUN
    serialize_state: CheckState = CheckState.NOT_RUN
    device_state: CheckState = CheckState.NOT_RUN
    constructor_signature: str | None = None
    formal_availability: FormalAvailability = FormalAvailability.EXECUTION_PENDING
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_formal_availability(self) -> RuntimeInventoryEntry:
        if self.formal_availability is FormalAvailability.FAILED and not self.errors:
            raise ValueError("FAILED inventory entries must contain at least one error")
        if self.formal_availability is not FormalAvailability.VERIFIED:
            return self
        if self.errors:
            raise ValueError("VERIFIED inventory entries cannot contain errors")
        required = [
            self.import_state,
            self.export_state,
            self.class_state,
            self.signature_state,
        ]
        if self.category is InventoryCategory.PYTORCH_ESTIMATOR:
            required.extend(
                [
                    self.constructor_state,
                    self.fit_state,
                    self.predict_state,
                    self.device_state,
                ]
            )
        elif self.category is InventoryCategory.NATIVE_PREDICTOR:
            required.extend([self.predict_state, self.device_state])
        elif self.category is InventoryCategory.DISTRIBUTION_OUTPUT:
            required.append(self.constructor_state)
        if any(state is not CheckState.PASS for state in required):
            raise ValueError("VERIFIED inventory entries require all category checks to PASS")
        return self


class RuntimeInventory(BaseModel):
    """Versioned inventory produced inside one isolated provider lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    generated_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    runtime_versions: dict[str, Any] = Field(default_factory=dict)
    entries: list[RuntimeInventoryEntry] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def summary(self) -> dict[str, Any]:
        by_category = {category.value: 0 for category in InventoryCategory}
        by_availability = {state.value: 0 for state in FormalAvailability}
        for entry in self.entries:
            by_category[entry.category.value] += 1
            by_availability[entry.formal_availability.value] += 1
        return {
            "total": len(self.entries),
            "by_category": by_category,
            "by_availability": by_availability,
            "formally_verified": by_availability[FormalAvailability.VERIFIED.value],
        }


def inventory_sha256(inventory: RuntimeInventory) -> str:
    """Hash canonical inventory JSON."""

    canonical = json.dumps(
        inventory.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
