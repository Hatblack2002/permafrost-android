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

/* ------------------------------------------------------------------ */
/* Desktop-GL / extension tokens the engine references but the NDK's
 * GLES headers do not declare. Values are the registry-assigned ones.
 *
 *   - GL_CLIP_DISTANCE0 and GL_TIMESTAMP are valid ES 3.0 entry points
 *     that the NDK gl3.h simply does not declare.
 *   - GL_CLIENT_STORAGE_BIT / GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT come
 *     with GL_EXT_buffer_storage on Android.
 *   - GL_TEXTURE_LOD_BIAS has no GLES 3.x equivalent; keeping the token
 *     lets the texture-state code compile, and the driver reports
 *     GL_INVALID_ENUM at runtime (logged by the engine's error check).
 *   - GL_DEPTH_COMPONENT32 is aliased to the ES-core 24-bit depth
 *     format so depth attachments request a supported internal format.
 *   - The pipeline-statistics and NVX gpu-memory query targets do not
 *     exist on GLES; the engine's feature flags (below) keep those
 *     code paths disabled at runtime.
 */
#ifndef GL_CLIP_DISTANCE0
#define GL_CLIP_DISTANCE0                    0x3000
#endif
#ifndef GL_TIMESTAMP
#define GL_TIMESTAMP                         0x8E28
#endif
#ifndef GL_CLIENT_STORAGE_BIT
#define GL_CLIENT_STORAGE_BIT                0x0200
#endif
#ifndef GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT
#define GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT  0x00004000
#endif
#ifndef GL_TEXTURE_MAX_ANISOTROPY_EXT
#define GL_TEXTURE_MAX_ANISOTROPY_EXT        0x84FE
#endif
#ifndef GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT
#define GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT    0x84FF
#endif
#ifndef GL_COMPRESSED_RGBA_S3TC_DXT5_EXT
#define GL_COMPRESSED_RGBA_S3TC_DXT5_EXT     0x83F3
#endif
#ifndef GL_TEXTURE_LOD_BIAS
#define GL_TEXTURE_LOD_BIAS                  0x8501
#endif

/* Pipeline statistics query targets (GL 4.6 ARB_pipeline_statistics_query). */
#ifndef GL_VERTICES_SUBMITTED
#define GL_VERTICES_SUBMITTED                0x82EE
#endif
#ifndef GL_PRIMITIVES_SUBMITTED
#define GL_PRIMITIVES_SUBMITTED              0x82EF
#endif
#ifndef GL_VERTEX_SHADER_INVOCATIONS
#define GL_VERTEX_SHADER_INVOCATIONS         0x82F0
#endif
#ifndef GL_CLIPPING_INPUT_PRIMITIVES
#define GL_CLIPPING_INPUT_PRIMITIVES         0x82F1
#endif
#ifndef GL_CLIPPING_OUTPUT_PRIMITIVES
#define GL_CLIPPING_OUTPUT_PRIMITIVES        0x82F2
#endif
#ifndef GL_FRAGMENT_SHADER_INVOCATIONS
#define GL_FRAGMENT_SHADER_INVOCATIONS       0x82F6
#endif

/* NVX_gpu_memory_info integer query targets (desktop-only extension). */
#ifndef GL_GPU_MEMORY_INFO_DEDICATED_VIDMEM_NVX
#define GL_GPU_MEMORY_INFO_DEDICATED_VIDMEM_NVX          0x9047
#endif
#ifndef GL_GPU_MEMORY_INFO_TOTAL_AVAILABLE_MEMORY_NVX
#define GL_GPU_MEMORY_INFO_TOTAL_AVAILABLE_MEMORY_NVX    0x9048
#endif
#ifndef GL_GPU_MEMORY_INFO_CURRENT_AVAILABLE_VIDMEM_NVX
#define GL_GPU_MEMORY_INFO_CURRENT_AVAILABLE_VIDMEM_NVX  0x9049
#endif
#ifndef GL_GPU_MEMORY_INFO_EVICTION_COUNT_NVX
#define GL_GPU_MEMORY_INFO_EVICTION_COUNT_NVX            0x904A
#endif
#ifndef GL_GPU_MEMORY_INFO_EVICTED_MEMORY_NVX
#define GL_GPU_MEMORY_INFO_EVICTED_MEMORY_NVX            0x904B
#endif

/* ES 3.x supports 24-bit fixed-point depth natively; alias the desktop
 * 32-bit internal format so depth attachments request a supported one. */
#ifndef GL_DEPTH_COMPONENT32
#define GL_DEPTH_COMPONENT32  GL_DEPTH_COMPONENT24
#endif

/* ------------------------------------------------------------------ */
/* GLEW compatibility surface. Upstream renderer code checks GLEW's
 * runtime feature globals; on Android they are provided by
 * android/port-src/pf_gl_android.c, which fills them in from the
 * driver's GL_EXTENSIONS string after the context is created
 * (pf_gl_detect_extensions).
 *
 * Features that are CORE in the port's GLES 3.2 target are compile-time
 * constants instead of runtime flags, matching PF_GL_HAS_* above.
 */
#define GLEW_ARB_copy_image   1  /* glCopyImageSubData: GLES 3.0 core   */
#define GLEW_KHR_debug        1  /* KHR_debug: GLES 3.2 core            */
#define GL_ARB_multi_draw_indirect 1  /* glMultiDrawArraysIndirect: ES 3.0 */

extern int GLEW_ARB_buffer_storage;              /* GL_EXT_buffer_storage          */
extern int GLEW_EXT_texture_compression_s3tc;    /* S3TC/DXT compression           */
extern int GLEW_EXT_texture_filter_anisotropic;  /* anisotropic filtering          */
extern int GLEW_ARB_pipeline_statistics_query;   /* absent on GLES: stays 0        */
extern int GLEW_NVX_gpu_memory_info;             /* absent on GLES: stays 0        */

void pf_gl_detect_extensions(void);

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
