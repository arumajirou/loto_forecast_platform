from loto.evaluation.path_codec import (
    decode_path_component,
    encode_path_component,
)


def test_baseline_colon_is_safe_and_reversible() -> None:
    logical = "baseline:fixed"

    encoded = encode_path_component(logical)

    assert encoded == "~YmFzZWxpbmU6Zml4ZWQ"
    assert ":" not in encoded
    assert decode_path_component(encoded) == logical


def test_safe_statsforecast_id_remains_unchanged() -> None:
    logical = "sf-autoarima"

    assert encode_path_component(logical) == logical
    assert decode_path_component(logical) == logical


def test_slash_and_underscore_do_not_collide() -> None:
    slash = encode_path_component("provider/model")
    underscore = encode_path_component("provider_model")

    assert slash != underscore
    assert "/" not in slash
    assert decode_path_component(slash) == "provider/model"


def test_windows_reserved_names_are_encoded() -> None:
    for logical in (
        "CON",
        "con",
        "NUL",
        "NUL.json",
        "COM1",
        "LPT9",
    ):
        encoded = encode_path_component(logical)

        assert encoded != logical
        assert decode_path_component(encoded) == logical


def test_trailing_dot_is_encoded() -> None:
    logical = "candidate."

    encoded = encode_path_component(logical)

    assert not encoded.endswith(".")
    assert decode_path_component(encoded) == logical


def test_percent_round_trip() -> None:
    logical = "candidate%experimental"

    encoded = encode_path_component(logical)

    assert decode_path_component(encoded) == logical
