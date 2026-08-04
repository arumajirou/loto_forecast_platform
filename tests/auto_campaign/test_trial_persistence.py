import pickle

from loto.auto_campaign import trial_persistence


class DummyAuto:
    pass


def test_persistent_class_is_stable_and_pickle_addressable() -> None:
    first = trial_persistence.persistent_auto_class(DummyAuto)
    second = trial_persistence.persistent_auto_class(DummyAuto)
    assert first is second
    assert getattr(trial_persistence, first.__name__) is first
    assert pickle.loads(pickle.dumps(first)) is first
