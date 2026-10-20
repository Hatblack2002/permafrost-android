#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/upstream.lock"
DEST="${1:-$ROOT/worktree/permafrost-engine}"
if [[ -e "$DEST/.git" ]]; then
  git -C "$DEST" fetch --depth 1 origin "$UPSTREAM_REF"
  git -C "$DEST" checkout --detach "$UPSTREAM_REF"
else
  mkdir -p "$(dirname "$DEST")"
  git clone --filter=blob:none --no-checkout "$UPSTREAM_URL" "$DEST"
  git -C "$DEST" fetch --depth 1 origin "$UPSTREAM_REF"
  git -C "$DEST" checkout --detach "$UPSTREAM_REF"
fi
printf 'Upstream pinned at %s\n' "$(git -C "$DEST" rev-parse HEAD)"
test "$(git -C "$DEST" rev-parse HEAD)" = "$UPSTREAM_REF"
