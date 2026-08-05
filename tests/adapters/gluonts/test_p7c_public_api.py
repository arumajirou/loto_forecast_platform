import loto.adapters.gluonts as gluonts


def test_p7c_public_api() -> None:
    assert gluonts.P7CRemediationPlan.__name__ == "P7CRemediationPlan"
    assert callable(gluonts.build_p7c_remediation_plan)
    assert callable(gluonts.verify_p7c_input)
    assert callable(gluonts.write_p7c_remediation_outputs)
