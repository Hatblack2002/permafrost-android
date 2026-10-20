/*
 * pf_gl.h — portable OpenGL entry header for the Permafrost Android port.
 *
 * This header is an Android-port adapter: it does not change desktop
 * behavior. Desktop builds keep the upstream GLEW include unchanged.
 * Android builds compile against the NDK's OpenGL ES 3.x headers instead
 * of desktop GL 3.3 + GLEW.
 *
 * Port target: OpenGL ES 3.2 (validated hardware target: Samsung Galaxy
 * S20 FE, Adreno 650, which exposes GLES 3.2). GLES 3.2 core covers:
 *   - instanced drawing (glDrawArraysInstanced, glVertexAttribDivisor)
 *   - 3D textures / texture arrays (glTexImage3D)
 *   - compute shaders and SSBOs (GLES 3.1 core)
 *   - geometry shaders and texture buffers (GLES 3.2 core)
 *   - KHR_debug (GLES 3.2 core)
 * Persistent buffer storage (GL 4.4 core / ARB_buffer_storage on desktop)
 * is provided by GL_EXT_buffer_storage on Android; see glBufferStorage
 * below.
 *
 * The GLES feature classification behind this header follows the shader
 * and renderer audit in scripts/audit-android-port.py.
 */
#ifndef PF_GL_H
#define PF_GL_H

#if defined(__ANDROID__)

#include <GLES3/gl3.h>
#include <GLES3/gl31.h>
#include <GLES3/gl32.h>

#define PF_GL_API_ES 1
/* KHR_debug is core in OpenGL ES 3.2. */
#define PF_GL_HAS_KHR_DEBUG 1
/* Persistent buffer storage via GL_EXT_buffer_storage. */
#define PF_GL_HAS_BUFFER_STORAGE 1

/* Some NDK toolchains only define the KHR_debug tokens under extension
 * guards; provide fallbacks so the renderer compiles unchanged. */
#ifndef GL_DEBUG_OUTPUT
#define GL_DEBUG_OUTPUT 0x92E0
#endif
#ifndef GL_DEBUG_OUTPUT_SYNCHRONOUS
#define GL_DEBUG_OUTPUT_SYNCHRONOUS 0x8242
#endif

/* GL_EXT_buffer_storage tokens (same values as GL 4.4 core). */
#ifndef GL_MAP_PERSISTENT_BIT
#define GL_MAP_PERSISTENT_BIT 0x0100
#endif
#ifndef GL_MAP_COHERENT_BIT
#define GL_MAP_COHERENT_BIT   0x0080
#endif

typedef void (GL_APIENTRYP PFNGLBUFFERSTORAGEEXTPROC)(
    GLenum target, GLsizeiptr size, const void *data, GLbitfield flags);

/*
 * glBufferStorage is not part of the GLES core symbol set; it is resolved
 * at runtime through EGL (glBufferStorage / glBufferStorageEXT). The
 * implementation lives in the Android shell's port sources
 * (pf_gl_android.c) and is linked into the native library.
 */
void glBufferStorage(GLenum target, GLsizeiptr size, const void *data,
                     GLbitfield flags);

#else /* !__ANDROID__ — desktop: preserve upstream GLEW behavior */

#include <GL/glew.h>

#endif /* __ANDROID__ */

#endif /* PF_GL_H */
