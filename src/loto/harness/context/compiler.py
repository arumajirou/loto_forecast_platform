from __future__ import annotations

from ..contracts import CompiledContext, ContextItem, ContextPriority
from ..security import sha256_text
from .compressor import StructuredCompactor
from .dedup import deduplicate_items
from .tokens import estimate_tokens

_PRIORITY_ORDER = {
    ContextPriority.PROTECTED: 0,
    ContextPriority.HIGH: 1,
    ContextPriority.NORMAL: 2,
    ContextPriority.LOW: 3,
}


class ContextCompiler:
    def __init__(self, total_tokens: int = 65536, output_reserve: int = 8192) -> None:
        if output_reserve >= total_tokens:
            raise ValueError("output reserve must be smaller than total context")
        self.total_tokens = total_tokens
        self.output_reserve = output_reserve
        self.input_budget = total_tokens - output_reserve
        self.compactor = StructuredCompactor()

    @staticmethod
    def _render(item: ContextItem) -> str:
        source = f" source={item.source}" if item.source else ""
        return f"<<<CONTEXT id={item.item_id} kind={item.kind}{source}>>>\n{item.content}"

    def _render_tokens(self, item: ContextItem) -> int:
        return estimate_tokens(self._render(item))

    def compile(self, items: list[ContextItem]) -> CompiledContext:
        measured = [
            item.model_copy(
                update={"token_estimate": item.token_estimate or estimate_tokens(item.content)}
            )
            for item in items
        ]
        raw_tokens = sum(item.token_estimate or 0 for item in measured)
        unique, duplicate_ids = deduplicate_items(measured)
        unique.sort(key=lambda item: (_PRIORITY_ORDER[item.priority], item.item_id))

        protected = [item for item in unique if item.priority == ContextPriority.PROTECTED]
        protected_tokens = sum(self._render_tokens(item) for item in protected)
        if protected_tokens > self.input_budget:
            raise ValueError(
                f"protected context ({protected_tokens}) exceeds input budget ({self.input_budget})"
            )

        selected: list[ContextItem] = list(protected)
        dropped = list(duplicate_ids)
        used = protected_tokens
        for item in unique:
            if item.priority == ContextPriority.PROTECTED:
                continue
            rendered_tokens = self._render_tokens(item)
            remaining = self.input_budget - used
            if rendered_tokens <= remaining:
                selected.append(item)
                used += rendered_tokens
                continue
            header_tokens = self._render_tokens(item.model_copy(update={"content": ""}))
            compact_budget = remaining - header_tokens
            if compact_budget >= 128 and item.priority in {
                ContextPriority.HIGH,
                ContextPriority.NORMAL,
            }:
                compacted = self.compactor.compact(item, compact_budget)
                compacted_tokens = self._render_tokens(compacted)
                if compacted_tokens <= remaining:
                    selected.append(compacted)
                    used += compacted_tokens
                    continue
            dropped.append(item.item_id)

        content = "\n\n".join(self._render(item) for item in selected)
        final_tokens = estimate_tokens(content)
        if final_tokens > self.input_budget:
            raise AssertionError(
                f"compiled context exceeded budget: {final_tokens} > {self.input_budget}"
            )
        selected_ids = [item.item_id for item in selected]
        protected_ids = {item.item_id for item in protected}
        protected_loss = len(protected_ids.difference(selected_ids))
        return CompiledContext(
            content=content,
            selected_ids=selected_ids,
            dropped_ids=dropped,
            raw_tokens=raw_tokens,
            final_tokens=final_tokens,
            compression_ratio=(final_tokens / raw_tokens) if raw_tokens else 1.0,
            protected_loss=protected_loss,
            context_sha256=sha256_text(content),
        )
