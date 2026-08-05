from loto.adapters import gluonts


def test_p7d_public_api_is_exported() -> None:
    assert gluonts.P7DBundleManifest.__name__ == "P7DBundleManifest"
    assert callable(gluonts.create_p7d_evidence_bundle)
    assert callable(gluonts.verify_p7d_evidence_bundle)
