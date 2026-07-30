"""protocol_hash must be stable, sensitive, and enforced."""
import pytest

from loto.evaluation.protocol import (
    ProtocolMismatch,
    ProtocolSpec,
    assert_comparable,
    protocol_hash,
)


def _spec(**overrides):
    base = dict(
        game="loto7", family="select", positions=7, universe_size=37,
        target_mode="position", horizon=1, data_version="v1",
        development_rows=140, holdout_rows=20, folds=2, test_size=3,
        min_train_size=80, objective_primary="position_mae",
    )
    base.update(overrides)
    return ProtocolSpec(**base)


def test_hash_is_stable_across_calls():
    assert _spec().hash == _spec().hash


def test_hash_is_insensitive_to_dict_ordering():
    a = _spec(objective_weights={"a": 1.0, "b": 2.0})
    b = _spec(objective_weights={"b": 2.0, "a": 1.0})
    assert a.hash == b.hash


@pytest.mark.parametrize(
    "override",
    [{"horizon": 4}, {"tau": 2}, {"game": "loto6"}, {"folds": 5},
     {"test_size": 10}, {"data_version": "v2"}, {"seeds": (1, 2)}],
)
def test_hash_changes_when_conditions_change(override):
    assert _spec().hash != _spec(**override).hash


def test_hash_length_is_sha256():
    assert len(_spec().hash) == 64


def test_assert_comparable_accepts_single_protocol():
    h = _spec().hash
    rows = [{"protocol_hash": h, "model_id": "a"}, {"protocol_hash": h, "model_id": "b"}]
    assert assert_comparable(rows) == h


def test_assert_comparable_refuses_mixed_protocols():
    rows = [
        {"protocol_hash": _spec().hash, "model_id": "a"},
        {"protocol_hash": _spec(horizon=4).hash, "model_id": "b"},
    ]
    with pytest.raises(ProtocolMismatch) as excinfo:
        assert_comparable(rows)
    assert "cross-protocol comparison refused" in str(excinfo.value)


def test_unlabelled_metric_is_a_distinct_protocol():
    """A missing protocol_hash must not be silently accepted as matching."""
    rows = [{"protocol_hash": _spec().hash, "model_id": "a"}, {"model_id": "b"}]
    with pytest.raises(ProtocolMismatch):
        assert_comparable(rows)


def test_empty_payload_hash_is_defined():
    assert len(protocol_hash({})) == 64
