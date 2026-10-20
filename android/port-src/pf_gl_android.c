/*
 * pf_gl_android.c — Android runtime resolution of glBufferStorage.
 *
 * Part of the Permafrost Android port adapter layer. This translation
 * unit is compiled only for Android builds (see android/app/jni/
 * Android-engine.mk) and provides the glBufferStorage symbol that the
 * engine's buffer-tracking wrappers call through pf_gl.h. On desktop the
 * symbol comes from GLEW's GL 4.4 / ARB_buffer_storage entry points and
 * this file is not compiled at all.
 *
 * GL_EXT_buffer_storage is exposed by Adreno and Mali GLES 3.2 drivers;
 * both the core-name and the EXT-suffix entry points are probed.
 */
#if defined(__ANDROID__)

#include "pf_gl.h"
#include <EGL/egl.h>
#include <stdbool.h>
#include <string.h>

static PFNGLBUFFERSTORAGEEXTPROC s_pf_gl_buffer_storage;
static int s_pf_gl_buffer_storage_resolved;

void glBufferStorage(GLenum target, GLsizeiptr size, const void *data,
                     GLbitfield flags)
{
    if(!s_pf_gl_buffer_storage_resolved) {
        s_pf_gl_buffer_storage =
            (PFNGLBUFFERSTORAGEEXTPROC)eglGetProcAddress("glBufferStorage");
        if(!s_pf_gl_buffer_storage) {
            s_pf_gl_buffer_storage = (PFNGLBUFFERSTORAGEEXTPROC)
                eglGetProcAddress("glBufferStorageEXT");
        }
        s_pf_gl_buffer_storage_resolved = 1;
    }

    if(s_pf_gl_buffer_storage)
        s_pf_gl_buffer_storage(target, size, data, flags);
}

/* ------------------------------------------------------------------ */
/* GLEW-compatible runtime feature flags (declared in pf_gl.h). They are
 * filled in from the current context's GL_EXTENSIONS string, mirroring
 * what GLEW does on desktop. Features that are core in the GLES 3.2
 * target are compile-time constants in pf_gl.h instead.
 */
int GLEW_ARB_buffer_storage              = 0;
int GLEW_EXT_texture_compression_s3tc    = 0;
int GLEW_EXT_texture_filter_anisotropic  = 0;
int GLEW_ARB_pipeline_statistics_query   = 0;  /* absent on GLES */
int GLEW_NVX_gpu_memory_info             = 0;  /* absent on GLES */

static bool pf_gl_has_extension(const unsigned char *exts, const char *name)
{
    return strstr((const char *)exts, name) != NULL;
}

void pf_gl_detect_extensions(void)
{
    /* glGetStringi enumerates the modern extension list; the legacy
     * glGetString(GL_EXTENSIONS) blob is still valid on GLES and is
     * enough for substring matching here. */
    const unsigned char *exts = glGetString(GL_EXTENSIONS);
    if(!exts)
        return;

    GLEW_ARB_buffer_storage = pf_gl_has_extension(exts, "GL_EXT_buffer_storage");
    GLEW_EXT_texture_compression_s3tc =
        pf_gl_has_extension(exts, "GL_EXT_texture_compression_s3tc")
        || pf_gl_has_extension(exts, "GL_NV_texture_compression_s3tc");
    GLEW_EXT_texture_filter_anisotropic =
        pf_gl_has_extension(exts, "GL_EXT_texture_filter_anisotropic");
}

#endif /* __ANDROID__ */
