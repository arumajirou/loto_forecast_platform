from loto.harness.context.compiler import ContextCompiler
from loto.harness.contracts import ContextItem, ContextPriority


def test_context_deduplicates_and_preserves_protected_items() -> None:
    protected = ContextItem(
        item_id="requirements",
        kind="requirements",
        content="Do not modify protected holdout. commit=abc123",
        priority=ContextPriority.PROTECTED,
    )
    duplicate = ContextItem(
        item_id="requirements-copy",
        kind="requirements",
        content="Do not modify protected holdout. commit=abc123",
        priority=ContextPriority.NORMAL,
    )
    noisy = ContextItem(
        item_id="log",
        kind="log",
        content="\n".join(
            [f"noise line {index}" for index in range(200)]
            + ["exit_code=1 ERROR failed"]
        ),
        priority=ContextPriority.HIGH,
    )
    compiled = ContextCompiler(total_tokens=700, output_reserve=100).compile(
        [protected, duplicate, noisy]
    )
    assert "requirements" in compiled.selected_ids
    assert "requirements-copy" in compiled.dropped_ids
    assert compiled.protected_loss == 0
    assert "commit=abc123" in compiled.content
    assert compiled.final_tokens < compiled.raw_tokens
    assert compiled.context_sha256


def test_protected_overflow_is_rejected() -> None:
    protected = ContextItem(
        item_id="huge",
        kind="source",
        content="重要" * 5000,
        priority=ContextPriority.PROTECTED,
    )
    try:
        ContextCompiler(total_tokens=1024, output_reserve=128).compile([protected])
    except ValueError as exc:
        assert "protected context" in str(exc)
    else:
        raise AssertionError("protected overflow must fail")
