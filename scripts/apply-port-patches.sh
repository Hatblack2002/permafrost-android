#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$ROOT/worktree/permafrost-engine}"
if [[ ! -d "$SRC/.git" ]]; then
  echo "Missing upstream worktree. Run scripts/prepare-upstream.sh first." >&2
  exit 2
fi
actual="$(git -C "$SRC" rev-parse HEAD)"
# shellcheck disable=SC1091
source "$ROOT/upstream.lock"
[[ "$actual" == "$UPSTREAM_REF" ]] || { echo "Refusing to patch unexpected upstream revision: $actual" >&2; exit 3; }
python3 "$ROOT/scripts/patch-raycast-touch.py" "$SRC"
echo "Touch adaptation applied. This is not yet a successful Android build."
