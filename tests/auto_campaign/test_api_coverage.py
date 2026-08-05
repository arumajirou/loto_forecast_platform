from loto.auto_campaign.api_coverage import api_case_plan


def test_api_case_ids_are_unique() -> None:
    cases = api_case_plan()
    assert len({case.case_id for case in cases}) == len(cases)
    assert any(case.argument == "distributed_config" for case in cases)
    assert any(case.argument == "callbacks" for case in cases)
    assert any(case.argument == "num_samples" and case.value == "30" for case in cases)
    assert any(case.argument == "cpus" and case.expected == "EXPECTED_ERROR" for case in cases)
    assert any(case.argument == "gpus" and case.expected == "EXPECTED_ERROR" for case in cases)
