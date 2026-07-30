from loto.evaluation.shadow import score_combination


def test_shadow_score():
    score = score_combination([1,2,3,4,5,6,7], [1,2,3,8,9,10,11])
    assert score["hits_at_7"] == 3
    assert 0 <= score["within_1_rate"] <= 1
