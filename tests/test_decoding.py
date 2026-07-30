import numpy as np

from loto.decoding.hybrid import decode_hybrid


def test_decoder_returns_legal_global_optimum():
    candidate = np.zeros(37)
    candidate[[0, 3, 8, 14, 21, 29, 36]] = 1.0
    position = np.zeros((7, 37))
    for pos, num in enumerate([1, 4, 9, 15, 22, 30, 37]):
        position[pos, num - 1] = 2.0
    result = decode_hybrid(candidate, position, top_k=5)
    assert result[0].numbers == [1, 4, 9, 15, 22, 30, 37]
    assert all(a < b for a, b in zip(result[0].numbers, result[0].numbers[1:]))


def test_decoder_never_returns_duplicates_even_when_one_number_dominates():
    candidate = np.zeros(37)
    candidate[18] = 100.0
    position = np.zeros((7, 37))
    result = decode_hybrid(candidate, position, top_k=1)[0]
    assert len(result.numbers) == len(set(result.numbers)) == 7
