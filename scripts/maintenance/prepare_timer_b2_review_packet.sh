#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"

fail() {
  echo
  echo "============================================================"
  echo "STOPPED SAFELY"
  echo "REASON=$1"
  echo "EXIT_CODE=${2:-1}"
  echo "============================================================"
  exit "${2:-1}"
}

[[ -f "$CTX" ]] || fail "missing context: $CTX"
# shellcheck disable=SC1090
source "$CTX"

cd "$WORKTREE" || fail "cannot enter worktree"

REV="70077a71acce1b4c00d98332fcaabc694255d8e5"
SNAP="$HOME/.cache/loto/timer-base-84m/snapshots/$REV"
PACKET="$EVIDENCE/timer-b2-human-review-packet.txt"
PACKET_SHA="$EVIDENCE/timer-b2-human-review-packet.sha256"
LOCK="environments/timer-base-84m-supported-py310/uv.lock"
LOCK_SHA_EXPECTED="5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0"

printf '=== 1. Verify exact local snapshot and lock ===\n'
[[ -d "$SNAP" ]] || fail "missing pinned snapshot: $SNAP"
[[ -f "$LOCK" ]] || fail "missing Timer lock"
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$LOCK_SHA_EXPECTED" ]] || fail "Timer lock SHA changed"

cat > "$EVIDENCE/timer-b2-expected-remote-code.sha256" <<'EOF'
bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173  configuration_timer.py
a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad  modeling_timer.py
357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1  ts_generation_mixin.py
EOF

(
  cd "$SNAP"
  sha256sum -c "$EVIDENCE/timer-b2-expected-remote-code.sha256"
) || fail "remote-code SHA verification failed"

echo "PASS EXACT_REMOTE_CODE_HASHES"

printf '\n=== 2. Build non-executing review packet ===\n'
SNAP="$SNAP" PACKET="$PACKET" LOCK_SHA_EXPECTED="$LOCK_SHA_EXPECTED" python3 - <<'PY'
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path

snap = Path(os.environ["SNAP"])
packet = Path(os.environ["PACKET"])
lock_sha = os.environ["LOCK_SHA_EXPECTED"]
files = [
    "configuration_timer.py",
    "modeling_timer.py",
    "ts_generation_mixin.py",
]
expected = {
    "configuration_timer.py": "bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173",
    "modeling_timer.py": "a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad",
    "ts_generation_mixin.py": "357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1",
}

risky_names = {
    "eval", "exec", "compile", "__import__", "open",
    "system", "popen", "run", "call", "check_call", "check_output",
    "urlopen", "request", "get", "post",
    "load", "loads", "pickle", "dumps",
    "CDLL", "PyDLL",
}

lines: list[str] = []
lines += [
    "TIMER BASE 84M - HUMAN REMOTE CODE REVIEW PACKET",
    "=================================================",
    "",
    "This packet is generated without importing or executing Timer remote code.",
    "It binds the review to exact SHA-256 values.",
    "",
    "Pinned model revision: 70077a71acce1b4c00d98332fcaabc694255d8e5",
    f"Dependency lock SHA-256: {lock_sha}",
    "",
    "Review decision is NOT automated. A named human must explicitly approve after reading this packet/source.",
    "",
]

for name in files:
    path = snap / name
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected[name]:
        raise SystemExit(f"hash mismatch for {name}: {digest}")
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=name)

    imports: list[str] = []
    defs: list[str] = []
    risky: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(f"function:{node.name}@L{node.lineno}")
        elif isinstance(node, ast.ClassDef):
            defs.append(f"class:{node.name}@L{node.lineno}")
        elif isinstance(node, ast.Call):
            func = node.func
            call_name = None
            if isinstance(func, ast.Name):
                call_name = func.id
            elif isinstance(func, ast.Attribute):
                call_name = func.attr
            if call_name in risky_names:
                risky.append(f"{call_name}@L{getattr(node, 'lineno', '?')}")

    lines += [
        f"FILE: {name}",
        "-" * (6 + len(name)),
        f"SHA-256: {digest}",
        f"Bytes: {len(raw)}",
        f"Imports: {', '.join(sorted(set(imports)))}",
        f"Definitions: {', '.join(defs)}",
        f"Risk-keyword calls requiring human interpretation: {', '.join(risky) if risky else 'NONE'}",
        "",
        "----- BEGIN EXACT SOURCE -----",
    ]
    for idx, source_line in enumerate(text.splitlines(), start=1):
        lines.append(f"{idx:05d}: {source_line}")
    lines += ["----- END EXACT SOURCE -----", "", ""]

lines += [
    "HUMAN CHECKLIST",
    "---------------",
    "Confirm there is no unacceptable subprocess/shell execution.",
    "Confirm there is no unacceptable network access.",
    "Confirm there is no eval/exec/dynamic import behavior that is unacceptable.",
    "Confirm there is no arbitrary credential/environment exfiltration.",
    "Confirm there is no arbitrary filesystem write or unsafe deserialization path.",
    "Confirm any torch/transformers load/generation calls are expected model behavior only.",
    "Confirm approval applies ONLY to the three exact SHA-256 values above and the exact dependency lock SHA.",
    "",
    "If approved, return the exact phrase:",
    "APPROVE TIMER BASE 84M EXACT BYTES AND LOCK",
]

packet.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

sha256sum "$PACKET" | tee "$PACKET_SHA"

printf '\n=== 3. Summary ===\n'
wc -l -c "$PACKET"
echo "PACKET=$PACKET"
echo "PACKET_SHA_FILE=$PACKET_SHA"
echo "REMOTE_CODE_IMPORTED=false"
echo "CHECKPOINT_LOADED=false"
echo "INFERENCE_EXECUTED=false"
echo
echo "STATUS=PHASE_B2_REVIEW_PACKET_READY"
echo "NEXT: review the packet, then explicitly approve or reject the exact bytes."
