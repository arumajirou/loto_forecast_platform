from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "scripts"
    / "experiments"
    / "run_numbers3_n1_tcn_exhaustive.py"
)
CONFIG = (
    ROOT
    / "configs"
    / "experiments"
    / "numbers3_n1_tcn_exhaustive.yaml"
)


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location(
        "tcn_exhaustive",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    value = importlib.util.module_from_spec(spec)

    # Python 3.13 dataclasses resolves postponed annotations
    # through sys.modules during class creation.
    sys.modules[spec.name] = value

    try:
        spec.loader.exec_module(value)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise

    return value


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(
        CONFIG.read_text(encoding="utf-8")
    )


def test_every_tcn_argument_is_classified(
    module,
    config,
):
    rows = module.inventory_arguments(config)
    assert rows
    assert not [
        row
        for row in rows
        if row["classification"] == "unclassified"
    ]


def test_combinations_are_complete_and_unique(
    module,
    config,
):
    combinations = module.build_combinations(config)
    expected = 1
    for values in config["search"].values():
        expected *= len(values)

    assert len(combinations) == expected
    assert len(
        {
            row["combination_id"]
            for row in combinations
        }
    ) == expected


def test_all_configured_search_arguments_exist(
    module,
    config,
):
    signature = module.tcn_signature()
    names = set(signature.parameters)
    unknown = sorted(
        set(config["search"]) - names
    )
    assert not unknown


def test_all_fixed_arguments_exist(
    module,
    config,
):
    signature = module.tcn_signature()
    names = set(signature.parameters)
    runtime_keys = set(config["runtime"])
    unknown = sorted(
        set(config["fixed"])
        - names
        - runtime_keys
    )
    assert not unknown


def test_constructor_and_property_reflection(
    module,
    config,
):
    combination = module.build_combinations(
        config
    )[0]
    seed = int(config["experiment"]["seeds"][0])
    kwargs = module.model_kwargs(
        config,
        combination,
        seed,
    )
    model = module.TCN(**kwargs)
    rows = module.verify_properties(
        model,
        kwargs,
        config,
        phase="constructed",
    )
    assert rows
    mismatches = [
        row
        for row in rows
        if not row["matched"]
    ]
    assert not mismatches, mismatches


def test_digitize_is_bounded(module):
    assert module.digitize(-100.0) == 0
    assert module.digitize(100.0) == 9
    assert module.digitize(4.49) == 4
    assert module.digitize(4.51) == 5


def test_valid_batch_size_none_resolves_to_batch_size(
    module,
    config,
):
    combination = module.build_combinations(
        config
    )[0]
    seed = int(config["experiment"]["seeds"][0])

    kwargs = module.model_kwargs(
        config,
        combination,
        seed,
    )

    assert kwargs["valid_batch_size"] is None

    model = module.TCN(**kwargs)

    rows = module.verify_properties(
        model,
        kwargs,
        config,
        phase="constructed",
    )

    row = next(
        item
        for item in rows
        if item["argument"] == "valid_batch_size"
    )

    assert row["matched"] is True
    assert (
        row["resolution_rule"]
        == "None resolves to batch_size"
    )
    assert row["effective_expected"] == (
        module.property_value_record(
            kwargs["batch_size"]
        )
    )
    assert row["actual"] == (
        module.property_value_record(
            kwargs["batch_size"]
        )
    )
