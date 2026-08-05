from __future__ import annotations

from dataclasses import dataclass


class LicensePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class LicenseDecision:
    code_license: str
    model_license: str
    license_lane: str
    research_only: bool
    production_champion_eligible: bool
    automatic_promotion: bool
    commercial_deployment_certified: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "code_license": self.code_license,
            "model_license": self.model_license,
            "license_lane": self.license_lane,
            "research_only": self.research_only,
            "production_champion_eligible": self.production_champion_eligible,
            "automatic_promotion": self.automatic_promotion,
            "commercial_deployment_certified": self.commercial_deployment_certified,
        }


def evaluate_license_lane(license_lane: str) -> LicenseDecision:
    if license_lane != "personal_noncommercial_research":
        raise LicensePolicyError(
            "Moirai 2.0 weights are fail-closed to personal non-commercial research"
        )
    return LicenseDecision(
        code_license="Apache-2.0",
        model_license="CC-BY-NC-4.0",
        license_lane=license_lane,
        research_only=True,
        production_champion_eligible=False,
        automatic_promotion=False,
        commercial_deployment_certified=False,
    )
