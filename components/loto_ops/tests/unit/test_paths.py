from loto_ops.paths import new_run_id


def test_new_run_id_prefix():
    assert new_run_id("x").startswith("x_")
