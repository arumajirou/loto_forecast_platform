from loto.moirai2_campaign.geometry import geometry_for_game


def test_required_game_geometries() -> None:
    expected = {
        "numbers3": (3, 0, 9, False),
        "numbers4": (4, 0, 9, False),
        "miniloto": (5, 1, 31, True),
        "loto6": (6, 1, 43, True),
        "loto7": (7, 1, 37, True),
    }
    for game_id, values in expected.items():
        geometry = geometry_for_game(game_id)
        assert (
            geometry.position_count,
            geometry.candidate_min,
            geometry.candidate_max,
            geometry.strictly_increasing,
        ) == values
