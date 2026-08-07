from __future__ import annotations

import re

_TOKENISH = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-independent estimate.

    Code and Japanese text are often denser than English prose, so this uses the
    larger of a lexical count and UTF-8 byte heuristic.
    """

    if not text:
        return 0
    lexical = len(_TOKENISH.findall(text))
    byte_estimate = (len(text.encode("utf-8")) + 3) // 4
    return max(lexical, byte_estimate)
