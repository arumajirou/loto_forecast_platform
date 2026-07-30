from __future__ import annotations

import numpy as np

from loto.coverage.auto_research import ExperimentProposal, _evaluate_general, _greedy_general, _legalize, _expand_space


def test_legalize_general():
    assert _legalize([1,1,2,40,5], 5, 31) == tuple(sorted(_legalize([1,1,2,40,5], 5, 31)))
    row = _legalize([1,1,2,40,5], 5, 31)
    assert len(row) == len(set(row)) == 5
    assert 1 <= row[0] < row[-1] <= 31


def test_evaluate_general_best_of_k():
    actual=np.array([[1,5,10,15,20],[2,6,11,16,21]])
    candidates=[(1,5,10,15,20),(2,6,11,16,21)]
    result=_evaluate_general(actual,candidates,1)
    assert result['row_within_tolerance']==1.0
    assert result['exact_row_rate']==1.0


def test_greedy_general_reaches_target():
    actual=np.array([[1,5,10,15,20],[2,6,11,16,21],[20,22,24,26,28]])
    pool=[(1,5,10,15,20),(20,22,24,26,28)]
    selected,trace=_greedy_general(actual,pool,target=.9,tolerance=1,max_candidates=5,diversity=0)
    assert len(selected)==2
    assert trace[-1]['coverage']==1.0


def test_expand_space_cartesian():
    rows=list(_expand_space({'alpha':[.1,1], 'window':[20,50]}))
    assert len(rows)==4
