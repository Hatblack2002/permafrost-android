#!/usr/bin/env python3
"""Add two-finger pinch zoom to Permafrost's RTS camera using SDL multi-gesture events."""
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engine")
path = root / "src/cam_control.c"
s = path.read_text()

anchor = """static void rts_cam_on_mousewheel(void *unused, void *event_arg)
"""
insert = """/* Android pinch zoom: SDL reports normalized distance deltas for a two-finger gesture. */
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

static void rts_cam_on_mousewheel(void *unused, void *event_arg)
"""
if "static void rts_cam_on_multigesture(void *unused, void *event_arg)" not in s:
    if anchor not in s: raise SystemExit("camera mousewheel anchor missing")
    s = s.replace(anchor, insert, 1)

old = """    E_Global_Register(SDL_MOUSEWHEEL,      rts_cam_on_mousewheel, NULL, G_RUNNING);
    E_Global_Register(EVENT_UPDATE_END,    rts_cam_on_update_end, NULL, 
"""
new = """    E_Global_Register(SDL_MOUSEWHEEL,      rts_cam_on_mousewheel, NULL, G_RUNNING);
    E_Global_Register(SDL_MULTIGESTURE,    rts_cam_on_multigesture, NULL, G_RUNNING);
    E_Global_Register(EVENT_UPDATE_END,    rts_cam_on_update_end, NULL, 
"""
if new not in s:
    old2 = """    E_Global_Register(SDL_MOUSEWHEEL,      rts_cam_on_mousewheel, NULL, G_RUNNING);
    E_Global_Register(EVENT_UPDATE_END,    rts_cam_on_update_end, NULL,
"""
    if old2 not in s: raise SystemExit("camera registration anchor missing")
    s = s.replace(old2, new, 1)

old = """    if(s_cam_ctx.installed_on_mousewheel) E_Global_Unregister(SDL_MOUSEWHEEL,       s_cam_ctx.installed_on_mousewheel);
    if(s_cam_ctx.installed_on_update_end) E_Global_Unregister(EVENT_UPDATE_END,    s_cam_ctx.installed_on_update_end);
"""
new = """    if(s_cam_ctx.installed_on_mousewheel) E_Global_Unregister(SDL_MOUSEWHEEL,       s_cam_ctx.installed_on_mousewheel);
    E_Global_Unregister(SDL_MULTIGESTURE, rts_cam_on_multigesture);
    if(s_cam_ctx.installed_on_update_end) E_Global_Unregister(EVENT_UPDATE_END,    s_cam_ctx.installed_on_update_end);
"""
if new not in s:
    if old not in s: raise SystemExit("camera unregister anchor missing")
    s = s.replace(old, new, 1)

path.write_text(s)
print(f"Applied pinch-zoom adaptation to {path}")
