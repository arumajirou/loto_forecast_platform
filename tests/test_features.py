import pandas as pd

from loto.data.canonical import canonicalize_loto7
from loto.features.pipeline import build_candidate_features


def test_features_for_draw_do_not_use_current_draw_target():
    rows = []
    for draw_no in range(1, 8):
        nums = [draw_no, draw_no + 5, draw_no + 10, draw_no + 15, draw_no + 20, draw_no + 25, draw_no + 30]
        rows.append({"draw_no": draw_no, "draw_date": f"2026-01-{draw_no:02d}", **{f"n{i+1}": n for i, n in enumerate(nums)}})
    master, _ = canonicalize_loto7(pd.DataFrame(rows))
    feats = build_candidate_features(master, windows=(3,))
    draw7 = feats[feats.draw_no == 7].set_index("candidate_number")
    # number 7 first appears in draw 2, not draw 7; current target must not increment history.
    assert draw7.loc[7, "freq_w3"] == 0.0
