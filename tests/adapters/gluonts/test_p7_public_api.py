from __future__ import annotations

from loto.adapters import gluonts


def test_p7_public_api_exports_are_available() -> None:
    assert len(gluonts.P7_EXPECTED_MODELS) == 9
    assert gluonts.P7EvidenceState.VALID.value == "VALID"
    assert gluonts.P7CertificationStatus.VERIFIED.value == "VERIFIED"
    assert callable(gluonts.audit_p7_lane)
    assert callable(gluonts.build_target_audit)
    assert callable(gluonts.parse_checksum_file)
    assert callable(gluonts.verify_checksum_inventory)
    assert callable(gluonts.write_target_audit)
