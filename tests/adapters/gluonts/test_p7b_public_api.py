from __future__ import annotations

import loto.adapters.gluonts as gluonts


def test_p7b_contract_is_exported() -> None:
    assert gluonts.P7BExecutionJournal.__name__ == "P7BExecutionJournal"
    assert gluonts.P7BExecutionManifest.__name__ == "P7BExecutionManifest"
    assert gluonts.P7BExecutionState.COMPLETED.value == "COMPLETED"
    assert gluonts.P7BStage.AUDIT.value == "audit"
    assert gluonts.P7BStageState.TIMED_OUT.value == "TIMED_OUT"
