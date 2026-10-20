#!/usr/bin/env python3
"""Apply the initial Android touch-pointer change to a pinned Permafrost checkout."""
from pathlib import Path
import sys

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("worktree/permafrost-engine")
path = source / "src/map/raycast.c"
text = path.read_text()

old = """static struct rc_ctx s_ctx;
"""
new = """static struct rc_ctx s_ctx;

/* SDL finger coordinates are normalized; retain drawable-pixel coordinates
 * so the existing world-space raycast math can be reused for touch input. */
static int s_touch_x;
static int s_touch_y;
static bool s_touch_active;
"""
if new not in text:
    if old not in text:
        raise SystemExit("Could not find raycast context anchor")
    text = text.replace(old, new, 1)

old = """static vec3_t rc_unproject_mouse_coords(float ndc_z)
{
    int mouse_x, mouse_y;
    SDL_GetMouseState(&mouse_x, &mouse_y);
"""
new = """static vec3_t rc_unproject_mouse_coords(float ndc_z)
{
    int mouse_x = 0, mouse_y = 0;
    if(s_touch_active) {
        mouse_x = s_touch_x;
        mouse_y = s_touch_y;
    } else {
        SDL_GetMouseState(&mouse_x, &mouse_y);
    }
"""
if new not in text:
    if old not in text:
        raise SystemExit("Could not find raycast coordinate anchor")
    text = text.replace(old, new, 1)

anchor = """static void on_render(void *user, void *event)
"""
handler = """static void on_touch_pointer(void *user, void *event)
{
    SDL_Event *sdl_event = (SDL_Event*)event;
    int width, height;
    Engine_WinDrawableSize(&width, &height);
    if(width <= 0 || height <= 0)
        return;

    switch(sdl_event->type) {
    case SDL_FINGERDOWN:
    case SDL_FINGERMOTION:
        s_touch_x = (int)(sdl_event->tfinger.x * width);
        s_touch_y = (int)(sdl_event->tfinger.y * height);
        s_touch_active = true;
        s_ctx.valid = false;
        rc_compute();
        break;
    case SDL_FINGERUP:
        s_touch_active = false;
        s_ctx.valid = false;
        break;
    default:
        break;
    }
}

"""
if handler not in text:
    if anchor not in text:
        raise SystemExit("Could not find render callback anchor")
    text = text.replace(anchor, handler + anchor, 1)

old = """    E_Global_Register(SDL_MOUSEMOTION, on_mousemove, NULL, G_RUNNING);
    E_Global_Register(EVENT_RENDER_3D_POST, on_render, NULL, G_RUNNING | G_PAUSED_FULL | G_PAUSED_UI_RUNNING);
"""
new = """    E_Global_Register(SDL_MOUSEMOTION, on_mousemove, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERDOWN, on_touch_pointer, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERMOTION, on_touch_pointer, NULL, G_RUNNING);
    E_Global_Register(SDL_FINGERUP, on_touch_pointer, NULL, G_RUNNING);
    E_Global_Register(EVENT_RENDER_3D_POST, on_render, NULL, G_RUNNING | G_PAUSED_FULL | G_PAUSED_UI_RUNNING);
"""
if new not in text:
    if old not in text:
        raise SystemExit("Could not find raycast event registration anchor")
    text = text.replace(old, new, 1)

old = """    E_Global_Unregister(SDL_MOUSEMOTION, on_mousemove);
    E_Global_Unregister(EVENT_RENDER_3D_POST, on_render);
"""
new = """    E_Global_Unregister(SDL_MOUSEMOTION, on_mousemove);
    E_Global_Unregister(SDL_FINGERDOWN, on_touch_pointer);
    E_Global_Unregister(SDL_FINGERMOTION, on_touch_pointer);
    E_Global_Unregister(SDL_FINGERUP, on_touch_pointer);
    E_Global_Unregister(EVENT_RENDER_3D_POST, on_render);
"""
if new not in text:
    if old not in text:
        raise SystemExit("Could not find raycast event unregister anchor")
    text = text.replace(old, new, 1)

old = """    s_ctx.valid = false;
}

void M_Raycast_SetHighlightSize(size_t size)
"""
new = """    s_ctx.valid = false;
    s_touch_active = false;
}

void M_Raycast_SetHighlightSize(size_t size)
"""
if new not in text:
    if old not in text:
        raise SystemExit("Could not find raycast uninstall anchor")
    text = text.replace(old, new, 1)

path.write_text(text)
print(f"Applied touch raycast change to {path}")
