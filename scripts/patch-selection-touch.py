#!/usr/bin/env python3
"""Add direct SDL finger handling to Permafrost's existing RTS selection module."""
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engine")
path = root / "src/game/selection.c"
s = path.read_text()

old = """static void on_mousemove(void *user, void *event)
{
    s_hovered_dirty = true;
}
"""
new = """/* Touch coordinates are in drawable pixels, matching the existing mouse path. */
static int s_touch_sel_x;
static int s_touch_sel_y;
static bool s_touch_sel_active;

static void on_touch_selection(void *user, void *event)
{
    SDL_Event *e = (SDL_Event*)event;
    int w, h;
    Engine_WinDrawableSize(&w, &h);
    if(w <= 0 || h <= 0)
        return;

    int x = (int)(e->tfinger.x * w);
    int y = (int)(e->tfinger.y * h);
    switch(e->type) {
    case SDL_FINGERDOWN:
        if(G_MouseOverMinimap() || S_UI_MouseOverWindow(x, y)
        || G_MouseInTargetMode() || G_Move_InOrderDrag())
            return;
        if(x <= 0 || x >= w-1 || y <= 0 || y >= h-1)
            return;
        s_touch_sel_x = x;
        s_touch_sel_y = y;
        s_touch_sel_active = true;
        s_ctx.state = STATE_MOUSE_SEL_DOWN;
        s_ctx.mouse_down_coord = (vec2_t){x, y};
        break;
    case SDL_FINGERMOTION:
        if(s_touch_sel_active) {
            s_touch_sel_x = x;
            s_touch_sel_y = y;
        }
        break;
    case SDL_FINGERUP:
        if(s_touch_sel_active && s_ctx.state == STATE_MOUSE_SEL_DOWN) {
            s_touch_sel_x = x;
            s_touch_sel_y = y;
            s_ctx.state = STATE_MOUSE_SEL_RELEASED;
            s_ctx.mouse_up_coord = (vec2_t){x, y};
            s_ctx.num_clicks = 1;
        }
        s_touch_sel_active = false;
        break;
    default:
        break;
    }
}

static void on_mousemove(void *user, void *event)
{
    s_hovered_dirty = true;
}
"""
if new not in s:
    if old not in s: raise SystemExit("selection mousemove anchor missing")
    s = s.replace(old, new, 1)

old = """    int mouse_x, mouse_y;
    SDL_GetMouseState(&mouse_x, &mouse_y);

    vec2_t signed_size = (vec2_t){mouse_x - s_ctx.mouse_down_coord.x, mouse_y - s_ctx.mouse_down_coord.y};
"""
new = """    int mouse_x, mouse_y;
    if(s_touch_sel_active) {
        mouse_x = s_touch_sel_x;
        mouse_y = s_touch_sel_y;
    } else {
        SDL_GetMouseState(&mouse_x, &mouse_y);
    }

    vec2_t signed_size = (vec2_t){mouse_x - s_ctx.mouse_down_coord.x, mouse_y - s_ctx.mouse_down_coord.y};
"""
if new not in s:
    if old not in s: raise SystemExit("selection render coordinate anchor missing")
    s = s.replace(old, new, 1)

old = """    E_Global_Register(SDL_MOUSEBUTTONDOWN, on_mousedown, NULL, G_RUNNING);
    E_Global_Register(SDL_MOUSEBUTTONUP,   on_mouseup, NULL, G_RUNNING);
    E_Global_Register(EVENT_RENDER_UI,     on_render_ui, NULL, G_RUNNING);
"""
new = """    E_Global_Register(SDL_MOUSEBUTTONDOWN, on_mousedown, NULL, G_RUNNING);
    E_Global_Register(SDL_MOUSEBUTTONUP,   on_mouseup, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERDOWN,      on_touch_selection, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERMOTION,    on_touch_selection, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERUP,        on_touch_selection, NULL, G_RUNNING);
    E_Global_Register(EVENT_RENDER_UI,     on_render_ui, NULL, G_RUNNING);
"""
if new not in s:
    if old not in s: raise SystemExit("selection registration anchor missing")
    s = s.replace(old, new, 1)

old = """    E_Global_Unregister(EVENT_RENDER_UI,     on_render_ui);
    E_Global_Unregister(SDL_MOUSEBUTTONUP,   on_mouseup);
    E_Global_Unregister(SDL_MOUSEBUTTONDOWN, on_mousedown);
"""
new = """    E_Global_Unregister(EVENT_RENDER_UI,     on_render_ui);
    E_Global_Unregister(SDL_FINGERUP,        on_touch_selection);
    E_Global_Unregister(SDL_FINGERMOTION,    on_touch_selection);
    E_Global_Unregister(SDL_FINGERDOWN,      on_touch_selection);
    E_Global_Unregister(SDL_MOUSEBUTTONUP,   on_mouseup);
    E_Global_Unregister(SDL_MOUSEBUTTONDOWN, on_mousedown);
    s_touch_sel_active = false;
"""
if new not in s:
    if old not in s: raise SystemExit("selection unregister anchor missing")
    s = s.replace(old, new, 1)

path.write_text(s)
print(f"Applied touch selection adaptation to {path}")
