#!/usr/bin/env python3
"""Add two-finger pinch zoom to Permafrost's RTS camera using SDL multi-gesture events."""
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engine")
path = root / "src/cam_control.c"
s = path.read_text()

handler = """/* Android pinch zoom: SDL reports normalized distance deltas for a two-finger gesture. */
static void rts_cam_on_multigesture(void *unused, void *event_arg)
{
    struct cam_rts_ctx *ctx = &s_cam_ctx.active_ctx.rts;
    SDL_MultiGestureEvent *e = (SDL_MultiGestureEvent*)event_arg;

    if(!s_rts_zoom_enabled || S_UI_TextEditHasFocus())
        return;

    /* Ignore tiny tracking noise; each accepted step is one existing zoom notch. */
    if(e->dDist > 0.012f)
        ctx->zoom_delta += 1;
    else if(e->dDist < -0.012f)
        ctx->zoom_delta -= 1;
}

"""
marker = "static void rts_cam_on_mousewheel(void *unused, void *event_arg)"
if "static void rts_cam_on_multigesture(void *unused, void *event_arg)" not in s:
    if marker not in s:
        raise SystemExit("camera mousewheel anchor missing")
    s = s.replace(marker, handler + marker, 1)

registration = "E_Global_Register(SDL_MOUSEWHEEL"
if "E_Global_Register(SDL_MULTIGESTURE,    rts_cam_on_multigesture" not in s:
    lines = s.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if registration in line:
            lines.insert(i + 1, "    E_Global_Register(SDL_MULTIGESTURE,    rts_cam_on_multigesture, NULL, G_RUNNING);\n")
            break
    else:
        raise SystemExit("camera mousewheel registration missing")
    s = "".join(lines)

unregistration = "E_Global_Unregister(SDL_MULTIGESTURE, rts_cam_on_multigesture);"
if unregistration not in s:
    lines = s.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if "E_Global_Unregister(EVENT_UPDATE_END" in line:
            lines.insert(i, "    E_Global_Unregister(SDL_MULTIGESTURE, rts_cam_on_multigesture);\n")
            break
    else:
        raise SystemExit("camera update-end unregistration anchor missing")
    s = "".join(lines)

path.write_text(s)
print(f"Applied pinch-zoom adaptation to {path}")
