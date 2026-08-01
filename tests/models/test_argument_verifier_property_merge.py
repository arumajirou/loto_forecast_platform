from loto.models.argument_verifier import (
    merge_effective_properties,
    verify_arguments,
)


def not_exposed(name: str) -> dict[str, str]:
    return {
        "property": name,
        "status": "NOT_EXPOSED",
        "reason": "not exposed by this adapter/model",
    }


def test_load_property_replaces_fit_not_exposed_seed() -> None:
    merged = merge_effective_properties(
        {
            "random_seed": not_exposed("random_seed"),
            "device": "cpu",
        },
        {
            "random_seed": 42,
            "effective_parameters": {
                "seed": 42,
                "device": "cpu",
            },
        },
    )

    rows = verify_arguments(
        {"seed": 42, "device": "cpu"},
        {"seed": 42, "device": "cpu"},
        merged,
    )

    by_argument = {row["argument"]: row for row in rows}

    assert by_argument["seed"]["effective_value"] == 42
    assert by_argument["seed"]["status"] == "VERIFIED"
    assert by_argument["device"]["effective_value"] == "cpu"
    assert by_argument["device"]["status"] == "VERIFIED"


def test_later_not_exposed_does_not_destroy_concrete_value() -> None:
    merged = merge_effective_properties(
        {
            "random_seed": 42,
            "effective_parameters": {"seed": 42},
        },
        {
            "random_seed": not_exposed("random_seed"),
            "effective_parameters": {},
        },
    )

    assert merged["random_seed"] == 42
    assert merged["effective_parameters"]["seed"] == 42
