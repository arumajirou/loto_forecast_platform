from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

UNFORMATTED_PATTERN = re.compile(r"^\s*-->\s+(.+?):\d+:\d+\s*$")


def read_baseline(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        raise RuntimeError(f"format baseline missing: {path}")
    rows: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value in rows:
            raise RuntimeError(f"duplicate baseline path: {value}")
        rows.add(value)
    return rows


def extract_unformatted(output: str) -> set[str]:
    paths: set[str] = set()
    for line in output.splitlines():
        match = UNFORMATTED_PATTERN.match(line)
        if match:
            paths.add(match.group(1))
    return paths


def classify(*, baseline: set[str], current: set[str]) -> tuple[set[str], set[str], set[str]]:
    inherited = baseline & current
    resolved = baseline - current
    introduced = current - baseline
    return inherited, resolved, introduced


def check_format(*, baseline_path: pathlib.Path, targets: list[str]) -> int:
    baseline = read_baseline(baseline_path)
    command = [sys.executable, "-m", "ruff", "format", "--check", *targets]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    if proc.returncode == 0:
        current: set[str] = set()
    elif proc.returncode == 1:
        current = extract_unformatted(combined)
        if not current:
            print(combined, file=sys.stderr)
            print("RUFF_FORMAT_BASELINE_TOOL_ERROR=unable_to_parse_failure", file=sys.stderr)
            return 2
    else:
        print(combined, file=sys.stderr)
        print(f"RUFF_FORMAT_BASELINE_TOOL_ERROR=ruff_exit_{proc.returncode}", file=sys.stderr)
        return proc.returncode
    inherited, resolved, introduced = classify(baseline=baseline, current=current)
    print(f"RUFF_FORMAT_BASELINE={len(baseline)}")
    print(f"RUFF_FORMAT_CURRENT={len(current)}")
    print(f"RUFF_FORMAT_INHERITED={len(inherited)}")
    print(f"RUFF_FORMAT_RESOLVED={len(resolved)}")
    print(f"RUFF_FORMAT_INTRODUCED={len(introduced)}")
    for path in sorted(inherited):
        print(f"INHERITED_FORMAT_DEBT={path}")
    for path in sorted(resolved):
        print(f"RESOLVED_FORMAT_DEBT={path}")
    for path in sorted(introduced):
        print(f"NEW_FORMAT_DEBT={path}", file=sys.stderr)
    if introduced:
        print("RUFF_FORMAT_BASELINE_GATE=FAIL", file=sys.stderr)
        return 1
    print("RUFF_FORMAT_BASELINE_GATE=PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reject new Ruff format debt beyond the baseline")
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("targets", nargs="+")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return check_format(baseline_path=args.baseline, targets=args.targets)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
