import pytest

from loto.orchestration.state_machine import RunStateMachine


def test_stage_order():
    sm = RunStateMachine(set())
    assert sm.next_stage() == "INGEST"
    with pytest.raises(RuntimeError):
        sm.mark_completed("TRAIN")
    sm.mark_completed("INGEST")
    assert sm.next_stage() == "VALIDATE"
