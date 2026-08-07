from __future__ import annotations

from difflib import SequenceMatcher

from ..contracts import ContextItem
from ..security import sha256_text


def deduplicate_items(
    items: list[ContextItem],
    *,
    near_duplicate_threshold: float = 0.97,
) -> tuple[list[ContextItem], list[str]]:
    kept: list[ContextItem] = []
    dropped: list[str] = []
    exact: set[str] = set()

    for item in items:
        normalized = "\n".join(line.rstrip() for line in item.content.strip().splitlines())
        digest = sha256_text(normalized)
        if digest in exact:
            dropped.append(item.item_id)
            continue
        duplicate = False
        for existing in kept:
            if abs(len(existing.content) - len(item.content)) > max(64, len(item.content) // 5):
                continue
            ratio = SequenceMatcher(None, existing.content, item.content, autojunk=True).ratio()
            if ratio >= near_duplicate_threshold:
                duplicate = True
                break
        if duplicate:
            dropped.append(item.item_id)
            continue
        exact.add(digest)
        kept.append(item)
    return kept, dropped
