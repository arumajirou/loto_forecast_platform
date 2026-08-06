from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from loto.data_access_ledger.contracts import STRICT_CONFIG
from loto.data_access_ledger.enums import (
    AccessDecision,
    FindingCode,
    FindingSeverity,
)

NON_CLAIMS = (
    "static ledger contract and pure validator only",
    "existing pipeline integration is not implemented",
    "real Train, Validation, Holdout, and Prospective data were not accessed",
    "fixture PASS is not certification of a real leakage-free campaign",
    "prediction lock cryptography and trusted time are not implemented",
    "actual source verification and runtime certification were not executed",
    "PostgreSQL, MLflow, Registry, and promotion are not connected",
)


class ValidationFinding(BaseModel):
    model_config = STRICT_CONFIG

    code: FindingCode
    severity: FindingSeverity
    event_id: str = "__ledger__"
    related_event_ids: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1, max_length=4000)
    expected: str = ""
    observed: str = ""


class ValidationReport(BaseModel):
    model_config = STRICT_CONFIG

    status: AccessDecision
    run_id: str
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    findings: list[ValidationFinding]
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    verified_event_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ValidationReport:
        errors = sum(item.severity is FindingSeverity.ERROR for item in self.findings)
        warnings = sum(item.severity is FindingSeverity.WARNING for item in self.findings)
        if self.error_count != errors or self.warning_count != warnings:
            raise ValueError("finding counts do not match findings")
        if errors and self.status is AccessDecision.PASS:
            raise ValueError("PASS is forbidden when errors exist")
        return self
