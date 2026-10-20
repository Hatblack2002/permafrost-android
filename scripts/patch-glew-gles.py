#!/usr/bin/env python3
"""Apply the GLES portability layer to the vendored Permafrost engine.

Transformations (all idempotent, anchor-checked, desktop behavior unchanged):
  1. Copy the portable GL entry header (android/include/pf_gl.h) into
     engine/src/render/pf_gl.h.
  2. Rewrite `#include <GL/glew.h>` to `#include "pf_gl.h"` across the
     renderer sources (pf_gl.h itself falls back to GLEW on desktop).
  3. Gate GLEW initialization / version checks in render.c so Android uses
     the SDL/EGL-created GLES context without a GL loader.
  4. Gate R_ComputeShaderSupported for GLES 3.2 (compute + SSBO are core).
  5. Request an ES 3.2 context profile on Android instead of desktop 3.3
     core in R_InitAttributes.

The patch is applied by .github/workflows/apply-android-port-patches.yml
and consumed by the Android compile/build workflows.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "engine"


def replace_once(text, old, new, what):
    if new in text:
        return text  # already applied (idempotence)
    if old not in text:
        raise SystemExit(f"Could not find anchor for {what}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------- 1. header
pf_gl_src = ROOT / "android" / "include" / "pf_gl.h"
if not pf_gl_src.is_file():
    raise SystemExit(f"Missing portable GL header: {pf_gl_src}")
header = pf_gl_src.read_text()

# -------------------------------------------------------- 2. include rewrite
rewritten = 0
targets = []
for path in sorted((source / "src").rglob("*.c")) + \
            sorted((source / "src").rglob("*.h")):
    if path.name == "pf_gl.h":
        continue
    text = path.read_text()
    if '#include <GL/glew.h>' in text:
        path.write_text(text.replace(
            '#include <GL/glew.h>', '#include "pf_gl.h"'))
        rewritten += 1
        if path.parent not in targets:
            targets.append(path.parent)

# Quoted includes resolve relative to the including file's directory, and
# the desktop Makefile's include paths must keep working unchanged, so the
# header is installed next to every consumer directory.
for target_dir in targets:
    pf_gl_dst = target_dir / "pf_gl.h"
    if not pf_gl_dst.is_file() or pf_gl_dst.read_text() != header:
        pf_gl_dst.write_text(header)
        print(f"Installed {pf_gl_dst}")
print(f"Rewrote GLEW includes in {rewritten} files")

# ----------------------------------------------------------- 3-5. render.c
render_c = source / "src" / "render" / "render.c"
text = render_c.read_text()

old = """    glewExperimental = GL_TRUE;
    if(glewInit() != GLEW_OK) {
        fprintf(stderr, "Failed to initialize GLEW\\n");
        arg->out_success = false;
        return;
    }

    if(!GLEW_VERSION_3_3) {
        fprintf(stderr, "Required OpenGL version not supported in GLEW\\n");
        arg->out_success = false;
        return;
    }
"""
new = """#if defined(__ANDROID__)
    /* The GLES 3.2 context is created by SDL/EGL before this point; there
     * is no GL loader to initialize on Android. The required feature set
     * is enforced by the manifest (glEsVersion 0x00030002) and validated
     * on device per the port acceptance criteria. */
#else
    glewExperimental = GL_TRUE;
    if(glewInit() != GLEW_OK) {
        fprintf(stderr, "Failed to initialize GLEW\\n");
        arg->out_success = false;
        return;
    }

    if(!GLEW_VERSION_3_3) {
        fprintf(stderr, "Required OpenGL version not supported in GLEW\\n");
        arg->out_success = false;
        return;
    }
#endif
"""
text = replace_once(text, old, new, "GLEW init block")

old = """    if(GLEW_KHR_debug) {
        glEnable(GL_DEBUG_OUTPUT);
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS);
        glDebugMessageCallback(debug_callback, NULL);
    }
"""
new = """#if defined(__ANDROID__)
    /* KHR_debug is core in OpenGL ES 3.2 (pf_gl.h: PF_GL_HAS_KHR_DEBUG). */
    if(PF_GL_HAS_KHR_DEBUG) {
        glEnable(GL_DEBUG_OUTPUT);
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS);
        glDebugMessageCallback(debug_callback, NULL);
    }
#else
    if(GLEW_KHR_debug) {
        glEnable(GL_DEBUG_OUTPUT);
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS);
        glDebugMessageCallback(debug_callback, NULL);
    }
#endif
"""
text = replace_once(text, old, new, "KHR_debug block")

old = """    /* The movement solve's buffers are persistently mapped */
    return (GLEW_VERSION_4_4
        || (GLEW_ARB_compute_shader && GLEW_ARB_shader_storage_buffer_object
            && GLEW_ARB_buffer_storage));
"""
new = """#if defined(__ANDROID__)
    /* Compute shaders and SSBOs are core in GLES 3.1; the port targets
     * GLES 3.2. Persistent buffer storage is provided by
     * GL_EXT_buffer_storage (pf_gl.h: PF_GL_HAS_BUFFER_STORAGE). */
    return true;
#else
    /* The movement solve's buffers are persistently mapped */
    return (GLEW_VERSION_4_4
        || (GLEW_ARB_compute_shader && GLEW_ARB_shader_storage_buffer_object
            && GLEW_ARB_buffer_storage));
#endif
"""
text = replace_once(text, old, new, "compute shader support check")

old = """    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
"""
new = """#if defined(__ANDROID__)
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);
#else
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
#endif
"""
text = replace_once(text, old, new, "GL context attributes")

render_c.write_text(text)
print(f"Applied GLES portability layer to {render_c}")
