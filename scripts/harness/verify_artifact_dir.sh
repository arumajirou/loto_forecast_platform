#!/usr/bin/env bash
set -Eeuo pipefail
TARGET="${1:?usage: verify_artifact_dir.sh ARTIFACT_DIR}"
TARGET="$(realpath "$TARGET")"
test -d "$TARGET"
test -f "$TARGET/SHA256SUMS"
(
  cd "$TARGET"
  sha256sum -c SHA256SUMS
)
echo "HARNESS_ARTIFACT=VERIFIED"
echo "artifact=$TARGET"
