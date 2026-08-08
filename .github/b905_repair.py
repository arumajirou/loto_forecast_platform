from __future__ import annotations

import ast
from pathlib import Path

# Read-only inventory run 31260664581 classified all 31 calls.
# True: equal-length invariant is already validated or should fail closed.
# False: intentional adjacent-pair traversal where seq and seq[1:] differ by one.
RULES: dict[str, dict[int, bool]] = {
    "scripts/certify_sundial_provider_v2.py": {367: True, 372: True},
    "scripts/verify_sundial_provider_v2_evidence.py": {122: True, 127: True},
    "src/loto/adapters/timesfm25/contracts.py": {194: False},
    "src/loto/autogluon_campaign/holdout_prospective.py": {
        277: True,
        279: False,
        287: True,
        319: True,
    },
    "src/loto/basicts_campaign/dataset.py": {47: False},
    "src/loto/coverage/instrumented_common.py": {80: False},
    "src/loto/darts_campaign/conformal_certification.py": {110: True},
    "src/loto/darts_campaign/ensemble_conformal_contract.py": {256: True},
    "src/loto/merlion_campaign/time_adapter.py": {45: False},
    "src/loto/neuralforecast/auto_frets/runtime_worker.py": {78: True, 80: True},
    "src/loto/neuralforecast/auto_segrnn/runtime_worker.py": {78: True, 80: True},
    "src/loto/neuralforecast/auto_timellm/runtime_worker.py": {72: True, 74: True},
    "src/loto/probabilistic/kdpp_history_source.py": {130: False},
    "src/loto/sktime_campaign/benchmark.py": {71: False},
    "src/loto/sktime_campaign/prospective.py": {68: False, 118: False},
    "src/loto/toto2_campaign/request_factory.py": {91: False},
    "tests/test_coverage_ledger.py": {74: False},
    "tests/test_pipeline_ledger_staged.py": {94: False},
    "tests/timesfm25_campaign/test_postprocess.py": {17: False},
}


def _expected_calls(path: str, line: int) -> int:
    if path.endswith("runtime_worker.py") and line in {80, 74}:
        return 2
    return 1


def _absolute_line_starts(source: str) -> list[int]:
    starts: list[int] = []
    total = 0
    for line in source.splitlines(keepends=True):
        starts.append(total)
        total += len(line)
    return starts


def _insertion(source: str, close_offset: int, strict: bool) -> str:
    index = close_offset - 1
    while index >= 0 and source[index].isspace():
        index -= 1
    prefix = "" if index >= 0 and source[index] == "," else ","
    return f"{prefix} strict={strict}"


def main() -> None:
    matched = 0
    strict_true = 0
    strict_false = 0

    for path_text, line_rules in RULES.items():
        path = Path(path_text)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path_text)
        starts = _absolute_line_starts(source)
        insertions: list[tuple[int, str]] = []
        found_per_line = {line: 0 for line in line_rules}

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "zip":
                continue
            if node.lineno not in line_rules:
                continue
            if any(keyword.arg == "strict" for keyword in node.keywords):
                raise SystemExit(f"{path_text}:{node.lineno}: strict already present")
            if node.end_lineno is None or node.end_col_offset is None:
                raise SystemExit(f"{path_text}:{node.lineno}: missing AST end position")

            absolute_end = starts[node.end_lineno - 1] + node.end_col_offset
            if source[absolute_end - 1] != ")":
                raise SystemExit(f"{path_text}:{node.lineno}: unexpected zip end")

            strict = line_rules[node.lineno]
            insertions.append((absolute_end - 1, _insertion(source, absolute_end - 1, strict)))
            found_per_line[node.lineno] += 1
            matched += 1
            strict_true += int(strict)
            strict_false += int(not strict)

        for line, count in found_per_line.items():
            expected = _expected_calls(path_text, line)
            if count != expected:
                raise SystemExit(
                    f"{path_text}:{line}: expected {expected} zip calls, got {count}"
                )

        for offset, insertion in sorted(insertions, reverse=True):
            source = source[:offset] + insertion + source[offset:]
        path.write_text(source, encoding="utf-8")

    if matched != 31:
        raise SystemExit(f"expected 31 classified zip calls, got {matched}")
    if strict_true != 18 or strict_false != 13:
        raise SystemExit(
            f"classification mismatch: strict_true={strict_true}, strict_false={strict_false}"
        )
    print(f"B905_CLASSIFIED_CALLS={matched}")
    print(f"STRICT_TRUE={strict_true}")
    print(f"STRICT_FALSE={strict_false}")


if __name__ == "__main__":
    main()
