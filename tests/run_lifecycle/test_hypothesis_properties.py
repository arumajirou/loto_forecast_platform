from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st

from loto.run_lifecycle import canonical_json, sha256_canonical

json_scalars = st.none() | st.booleans() | st.integers() | st.text()
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(min_size=1, max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)


@given(st.dictionaries(st.text(min_size=1, max_size=8), json_values, max_size=6))
def test_canonicalization_is_deterministic(value) -> None:
    assert canonical_json(value) == canonical_json(value)
    assert sha256_canonical(value) == sha256_canonical(value)


@given(st.text(min_size=1))
def test_hash_changes_for_changed_payload(value: str) -> None:
    assert sha256_canonical({"value": value}) != sha256_canonical({"value": value + "-changed"})
