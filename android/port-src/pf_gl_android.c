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

#endif /* __ANDROID__ */
