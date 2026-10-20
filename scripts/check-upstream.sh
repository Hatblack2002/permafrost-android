#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/upstream.lock"
SRC="${1:-$ROOT/worktree/permafrost-engine}"
if [[ ! -d "$SRC/.git" ]]; then
  echo "Missing upstream worktree. Run scripts/prepare-upstream.sh first." >&2
  exit 2
fi
actual="$(git -C "$SRC" rev-parse HEAD)"
[[ "$actual" == "$UPSTREAM_REF" ]] || { echo "Wrong upstream revision: $actual" >&2; exit 3; }
echo "Pinned revision verified: $actual"
echo
echo "Desktop GL/GLEW and mouse-input references to port:"
grep -nE 'glewInit|SDL_GL_CreateContext|SDL_GetMouseState|SDL_MOUSEBUTTON|SDL_MOUSEMOTION' \
  "$SRC/src/render/render.c" "$SRC/src/map/raycast.c" "$SRC/src/cursor.c" \
  "$SRC/src/cam_control.c" "$SRC/src/game/selection.c" "$SRC/src/map/minimap.c" || true
