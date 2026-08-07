from __future__ import annotations

import re

from ..contracts import ContextItem
from .tokens import estimate_tokens

_IMPORTANT_LINE = re.compile(
    r"(?i)(error|failed|failure|traceback|exception|exit_code|status=|commit|branch|sha256|"
    r"pytest|ruff|mypy|warning|blocked|verified|command=|objective|acceptance)"
)


class StructuredCompactor:
    def compact(self, item: ContextItem, target_tokens: int) -> ContextItem:
        current = item.token_estimate or estimate_tokens(item.content)
        if current <= target_tokens:
            return item.model_copy(update={"token_estimate": current})
        lines = item.content.splitlines()
        selected: list[str] = []
        seen: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            if _IMPORTANT_LINE.search(stripped):
                selected.append(line)
                seen.add(stripped)
        if not selected:
            head_count = max(1, len(lines) // 4)
            selected = lines[:head_count] + ["... [compacted] ..."] + lines[-head_count:]
        content = "\n".join(selected)
        while estimate_tokens(content) > target_tokens and len(selected) > 4:
            selected = selected[: len(selected) // 2] + ["... [compacted] ..."] + selected[-2:]
            content = "\n".join(selected)
        return item.model_copy(
            update={
                "content": content,
                "token_estimate": estimate_tokens(content),
                "metadata": {**item.metadata, "compacted": True, "raw_tokens": current},
            }
        )
