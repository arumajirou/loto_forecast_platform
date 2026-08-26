#!/usr/bin/env bash
set -Eeuo pipefail

# Safe launcher for phase4c_publish_verified_local.sh.
#
# The original Phase 4C local verifier writes SHA256SUMS inside its EXIT trap
# and then emits final lines through tee, so run.log legitimately grows after
# its recorded checksum. This launcher keeps the original manifest unchanged
# but patches a temporary copy of the publisher so only that known mutable
# run.log entry is excluded from sha256sum -c. All other recorded files remain
# checksum-gated.

HANDOFF_WT="${LOTO_HANDOFF_WT:-/mnt/e/env/ts/worktrees/loto-runtime-handoff}"
CORE="$HANDOFF_WT/handoff/tools/phase4c_publish_verified_local.sh"

if [[ ! -f "$CORE" ]]; then
  echo "PHASE4C_SAFE_PUBLISH=BLOCKED"
  echo "REASON=CORE_PUBLISHER_NOT_FOUND:$CORE"
  exit 2
fi

TMP="$(mktemp /tmp/phase4c-publish-safe.XXXXXX.sh)"
cleanup() {
  rm -f "$TMP"
}
trap cleanup EXIT

python3 - "$CORE" "$TMP" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text("utf-8")

old = '''echo
echo "=== 2. LOCAL SHA-256 VERIFY ==="
(
  cd /
  sha256sum -c "$OUT/SHA256SUMS"
)
echo "LOCAL_SHA256_GATE=PASS"
'''

new = '''echo
echo "=== 2. LOCAL SHA-256 VERIFY ==="
VERIFY_SUMS="$(mktemp /tmp/phase4c-local-sha256.XXXXXX)"
python3 - "$OUT/SHA256SUMS" "$VERIFY_SUMS" "$OUT/run.log" <<'PY_SHA_FILTER'
from __future__ import annotations

import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
mutable_log = Path(sys.argv[3]).resolve()

kept: list[str] = []
skipped: list[str] = []
for raw in source.read_text("utf-8").splitlines():
    if not raw.strip():
        continue
    parts = raw.split("  ", 1)
    if len(parts) != 2:
        raise SystemExit(f"INVALID_SHA256SUMS_LINE: {raw!r}")
    recorded_path = Path(parts[1])
    try:
        resolved = recorded_path.resolve()
    except OSError:
        resolved = recorded_path
    if resolved == mutable_log:
        skipped.append(raw)
    else:
        kept.append(raw)

if not skipped:
    raise SystemExit("EXPECTED_MUTABLE_RUN_LOG_ENTRY_NOT_FOUND")

target.write_text("\\n".join(kept) + "\\n", encoding="utf-8")
print(f"SHA256_ENTRIES_VERIFIED={len(kept)}")
print(f"SHA256_ENTRIES_SKIPPED_MUTABLE_RUN_LOG={len(skipped)}")
PY_SHA_FILTER
(
  cd /
  sha256sum -c "$VERIFY_SUMS"
)
rm -f "$VERIFY_SUMS"
echo "RUN_LOG_CURRENT_SHA256=$(sha256sum "$OUT/run.log" | awk '{print $1}')"
echo "RUN_LOG_CHECKSUM_POLICY=RECORDED_MANIFEST_ENTRY_SKIPPED_BECAUSE_LOG_GREW_AFTER_EXIT_TRAP_HASH"
echo "LOCAL_SHA256_GATE=PASS_WITH_KNOWN_MUTABLE_RUN_LOG"
'''

count = text.count(old)
if count != 1:
    raise SystemExit(f"CHECKSUM_BLOCK_MATCH_COUNT={count}; expected 1")

patched = text.replace(old, new, 1)
dst.write_text(patched, encoding="utf-8")
PY

bash -n "$TMP"
echo "PHASE4C_SAFE_PUBLISHER_SYNTAX=PASS"

# Pass through the optional explicit artifact directory unchanged.
bash "$TMP" "$@"
