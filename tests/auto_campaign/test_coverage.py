from loto.auto_campaign.coverage import build_pairwise_plan, coverage_report


def test_pairwise_plan_has_full_coverage() -> None:
    levels = {"a": [1, 2], "b": ["x", "y", "z"], "c": [False, True]}
    rows = build_pairwise_plan(levels)
    report = coverage_report(levels, rows)
    assert report["coverage_rate"] == 1.0
    assert report["missing_pairs"] == []
