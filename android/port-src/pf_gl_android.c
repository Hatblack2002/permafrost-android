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

/* ------------------------------------------------------------------ */
/* Desktop-GL link shims.
 *
 * The engine was written against desktop OpenGL. The GLES portability
 * header (pf_gl.h) maps tokens and flags, but a handful of desktop
 * entry points still end up referenced from the engine objects and have
 * no export in the NDK's GLESv3 stub for the android-24 target:
 *
 *   glPointSize, glProvokingVertex, glDrawBuffer        (no ES equivalent)
 *   glGetTexImage, glGetTextureSubImage                 (no ES equivalent)
 *   glGetQueryObjectui64v                               (EXT-only on GLES)
 *   glMapBuffer, glQueryCounter, glGetQueryObjectiv,
 *   glMultiDrawArraysIndirect                           (ES core, but not
 *                    exported by the android-24 GLESv3 stub build used)
 *
 * Core functions are forwarded through eglGetProcAddress (which the
 * Adreno/Mali drivers answer even for core entry points); genuinely
 * missing functionality is emulated (FBO readback) or made a no-op
 * where the ES behavior already matches the requested state.
 */
#include <GLES3/gl31.h>

#include <android/log.h>
#include <dlfcn.h>
#include <stdio.h>

/* Resolve a GLES core/extension entry point from the actual driver
 * library. Two pitfalls to avoid:
 *   - eglGetProcAddress may return NULL for core (non-extension)
 *     functions on some implementations;
 *   - dlsym(RTLD_DEFAULT, ...) would find THIS library's own shim
 *     definitions and turn the forwarders into infinite recursion.
 * dlopen(NOLOAD) on libGLESv3.so answers both: it is already loaded by
 * the time any GL call runs, and it only contains the real exports.
 */
static void *pf_gl_resolve_core(const char *name)
{
    static void *glesv3;
    if(!glesv3)
        glesv3 = dlopen("libGLESv3.so", RTLD_NOW | RTLD_NOLOAD);
    if(glesv3) {
        void *fn = dlsym(glesv3, name);
        if(fn)
            return fn;
    }
    return eglGetProcAddress(name);
}

/* ---- per-texture size tracking for the readback shims ------------- */
#define PF_GL_TRACK_MAX 256
struct pf_tex_size { GLuint id; GLint w, h, d; };
static struct pf_tex_size s_tex_sizes[PF_GL_TRACK_MAX];
static int s_tex_size_count;

static void pf_tex_record(GLuint id, GLint w, GLint h, GLint d)
{
    for(int i = 0; i < s_tex_size_count; i++) {
        if(s_tex_sizes[i].id == id) {
            s_tex_sizes[i].w = w; s_tex_sizes[i].h = h; s_tex_sizes[i].d = d;
            return;
        }
    }
    if(s_tex_size_count < PF_GL_TRACK_MAX) {
        s_tex_sizes[s_tex_size_count++] =
            (struct pf_tex_size){ id, w, h, d };
    }
}

static bool pf_tex_lookup(GLuint id, GLint *w, GLint *h, GLint *d)
{
    for(int i = 0; i < s_tex_size_count; i++) {
        if(s_tex_sizes[i].id == id) {
            *w = s_tex_sizes[i].w; *h = s_tex_sizes[i].h; *d = s_tex_sizes[i].d;
            return true;
        }
    }
    return false;
}

/* Wrap the size-carrying upload entry points so the readback shims know
 * the dimensions (GLES has no glGetTexLevelParameter query). */
void glTexImage2D(GLenum target, GLint level, GLint internalformat,
                  GLsizei width, GLsizei height, GLint border,
                  GLenum format, GLenum type, const void *pixels);
void glTexImage2D(GLenum target, GLint level, GLint internalformat,
                  GLsizei width, GLsizei height, GLint border,
                  GLenum format, GLenum type, const void *pixels)
{
    typedef void (*pf_teximg2d_t)(GLenum, GLint, GLint, GLsizei, GLsizei,
                                  GLint, GLenum, GLenum, const void *);
    static pf_teximg2d_t real;
    if(!real)
        real = (pf_teximg2d_t)pf_gl_resolve_core("glTexImage2D");
    if(real)
        real(target, level, internalformat, width, height, border,
             format, type, pixels);

    if(level == 0 && width > 0 && height > 0) {
        GLint bound = 0;
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &bound);
        pf_tex_record((GLuint)bound, width, height, 1);
    }
}
                  GLsizei width, GLsizei height, GLsizei depth,
                  GLint border, GLenum format, GLenum type,
                  const void *pixels);
void glTexImage3D(GLenum target, GLint level, GLint internalformat,
typedef void (*pf_gl_teximg3d_t)(GLenum, GLint, GLint, GLsizei, GLsizei,
                                 GLsizei, GLint, GLenum, GLenum,
                                 const void *);
void glTexImage3D(GLenum target, GLint level, GLint internalformat,
                  GLsizei width, GLsizei height, GLsizei depth,
                  GLint border, GLenum format, GLenum type,
                  const void *pixels);
void glTexImage3D(GLenum target, GLint level, GLint internalformat,
                  GLsizei width, GLsizei height, GLsizei depth,
                  GLint border, GLenum format, GLenum type,
                  const void *pixels)
{
    static pf_gl_teximg3d_t real;
    if(!real)
        real = (pf_gl_teximg3d_t)pf_gl_resolve_core("glTexImage3D");
    if(real)
        real(target, level, internalformat, width, height, depth,
             border, format, type, pixels);

    if(level == 0 && width > 0 && height > 0 && depth > 0) {
        GLint bound = 0;
        glGetIntegerv(GL_TEXTURE_BINDING_2D_ARRAY, &bound);
        pf_tex_record((GLuint)bound, width, height, depth);
    }
}

static int pf_gl_bytes_per_pixel(GLenum format, GLenum type)
{
    (void)type;
    switch(format) {
    case GL_RGBA: return 4;
    case GL_RGB:  return 3;
    case GL_RG:   return 2;
    case GL_RED:  return 1;
    default:      return 4;
    }
}

static void pf_gl_log_once(const char *msg)
{
    static int logged;
    if(!logged) {
        logged = 1;
        __android_log_print(ANDROID_LOG_WARN, "pf-gl",
                            "gl shim: %s", msg);
    }
}

/* ---- trivial no-op shims ------------------------------------------ */
void glPointSize(GLfloat size);
void glPointSize(GLfloat size)
{
    (void)size; /* GLES 3 renders points at 1px; the debug path that
                 * enlarges them is cosmetic-only. */
}

void glProvokingVertex(GLenum mode);
void glProvokingVertex(GLenum mode)
{
    (void)mode; /* GLES follows the first-vertex convention by spec,
                 * which is what the engine requests. */
}

void glDrawBuffer(GLenum buf);
void glDrawBuffer(GLenum buf)
{
    /* ES only has the array form; a single-color-attachment draw buffer
     * is expressible through it. */
    if(buf != GL_NONE && buf != GL_BACK)
        glDrawBuffers(1, &buf);
}

/* ---- core entry points missing from the stub: forward -------------- */
void *glMapBuffer(GLenum target, GLenum access);
void *glMapBuffer(GLenum target, GLenum access)
{
    typedef void *(*pf_mapbuffer_t)(GLenum, GLenum);
    static pf_mapbuffer_t real;
    if(!real)
        real = (pf_mapbuffer_t)pf_gl_resolve_core("glMapBuffer");
    if(real)
        return real(target, access);

    /* Fallback: whole-buffer range map. */
    GLint size = 0;
    glGetBufferParameteriv(target, GL_BUFFER_SIZE, &size);
    GLbitfield bits = GL_MAP_READ_BIT | GL_MAP_WRITE_BIT;
    if(access == GL_READ_ONLY)
        bits = GL_MAP_READ_BIT;
    else if(access == GL_WRITE_ONLY)
        bits = GL_MAP_WRITE_BIT;
    return glMapBufferRange(target, 0, size, bits);
}

void glQueryCounter(GLuint id, GLenum target);
void glQueryCounter(GLuint id, GLenum target)
{
    typedef void (*pf_querycounter_t)(GLuint, GLenum);
    static pf_querycounter_t real;
    if(!real)
        real = (pf_querycounter_t)pf_gl_resolve_core("glQueryCounter");
    if(real)
        real(id, target);
}

void glGetQueryObjectiv(GLuint id, GLenum pname, GLint *params);
void glGetQueryObjectiv(GLuint id, GLenum pname, GLint *params)
{
    typedef void (*pf_getqoiv_t)(GLuint, GLenum, GLint *);
    static pf_getqoiv_t real;
    if(!real)
        real = (pf_getqoiv_t)pf_gl_resolve_core("glGetQueryObjectiv");
    if(real)
        real(id, pname, params);
}

void glMultiDrawArraysIndirect(GLenum mode, const void *indirect,
                               GLsizei count, GLsizei stride);
void glMultiDrawArraysIndirect(GLenum mode, const void *indirect,
                               GLsizei count, GLsizei stride)
{
    typedef void (*pf_mdi_t)(GLenum, const void *, GLsizei, GLsizei);
    static pf_mdi_t real;
    if(!real) {
        real = (pf_mdi_t)pf_gl_resolve_core("glMultiDrawArraysIndirect");
        if(!real)
            real = (pf_mdi_t)eglGetProcAddress("glMultiDrawArraysIndirectEXT");
    }
    if(real)
        real(mode, indirect, count, stride);
}

/* 64-bit query results: GLES only defines the EXT variant; fall back to
 * the 32-bit core getter (ns timestamps wrap ~every 4.3s, acceptable
 * only as a last resort for the GPU-trace path). */
void glGetQueryObjectui64v(GLuint id, GLenum pname, GLuint64 *params);
void glGetQueryObjectui64v(GLuint id, GLenum pname, GLuint64 *params)
{
    typedef void (*pf_getqo64_t)(GLuint, GLenum, GLuint64 *);
    static pf_getqo64_t ext;
    if(!ext)
        ext = (pf_getqo64_t)eglGetProcAddress("glGetQueryObjectui64vEXT");
    if(ext) {
        ext(id, pname, params);
        return;
    }
    GLuint lo = 0;
    glGetQueryObjectuiv(id, pname, &lo);
    *params = (GLuint64)lo;
    pf_gl_log_once("64-bit query results unavailable; using 32-bit wrap");
}

/* ---- FBO-based readback shims -------------------------------------- */
void glGetTexImage(GLenum target, GLint level, GLenum format, GLenum type,
                   void *pixels);
void glGetTexImage(GLenum target, GLint level, GLenum format, GLenum type,
                   void *pixels)
{
    GLint w = 0, h = 0, d = 1;
    GLint bound = 0;
    GLenum binding;
    if(target == GL_TEXTURE_2D) {
        binding = GL_TEXTURE_BINDING_2D;
        glGetIntegerv(binding, &bound);
    } else if(target == GL_TEXTURE_2D_ARRAY) {
        binding = GL_TEXTURE_BINDING_2D_ARRAY;
        glGetIntegerv(binding, &bound);
    } else {
        pf_gl_log_once("glGetTexImage: unsupported target");
        return;
    }
    if(!pf_tex_lookup((GLuint)bound, &w, &h, &d)) {
        pf_gl_log_once("glGetTexImage: size of bound texture unknown");
        return;
    }

    GLint prev_read_fbo = 0, prev_draw_fbo = 0;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &prev_read_fbo);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &prev_draw_fbo);

    GLuint fbo = 0;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);

    int bpp = pf_gl_bytes_per_pixel(format, type);
    if(target == GL_TEXTURE_2D) {
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, (GLuint)bound, level);
        glReadPixels(0, 0, w, h, format, type, pixels);
    } else {
        for(int layer = 0; layer < d; layer++) {
            glFramebufferTextureLayer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                      (GLuint)bound, level, layer);
            glReadPixels(0, 0, w, h, format, type,
                         (char *)pixels + (size_t)layer * w * h * bpp);
        }
    }

    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, (GLuint)prev_draw_fbo);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)prev_read_fbo);
    glDeleteFramebuffers(1, &fbo);
}

void glGetTextureSubImage(GLuint texture, GLint level, GLint xoffset,
                          GLint yoffset, GLint zoffset, GLsizei width,
                          GLsizei height, GLsizei depth, GLenum format,
                          GLenum type, GLsizei bufSize, void *pixels);
void glGetTextureSubImage(GLuint texture, GLint level, GLint xoffset,
                          GLint yoffset, GLint zoffset, GLsizei width,
                          GLsizei height, GLsizei depth, GLenum format,
                          GLenum type, GLsizei bufSize, void *pixels)
{
    (void)bufSize;
    GLint prev_read_fbo = 0, prev_draw_fbo = 0;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &prev_read_fbo);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &prev_draw_fbo);

    GLuint fbo = 0;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);

    int bpp = pf_gl_bytes_per_pixel(format, type);
    size_t layer_pitch = (size_t)width * height * bpp;
    for(int z = 0; z < depth; z++) {
        glFramebufferTextureLayer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                  texture, level, zoffset + z);
        glReadPixels(xoffset, yoffset, width, height, format, type,
                     (char *)pixels + (size_t)z * layer_pitch);
    }

    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, (GLuint)prev_draw_fbo);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)prev_read_fbo);
    glDeleteFramebuffers(1, &fbo);
}

/* ---- bionic compatibility ------------------------------------------ */
/* mimalloc maps its arenas through memfd_create, which bionic only
 * exports from API 28; the ndk-build target is android-24. Route
 * through the raw syscall (kernel >= 3.17, all 64-bit devices). */
#include <errno.h>
#include <sys/syscall.h>
#include <unistd.h>

#if __ANDROID_API__ < 28
#ifndef SYS_memfd_create
#define SYS_memfd_create 279 /* aarch64 */
#endif
int memfd_create(const char *name, unsigned int flags);
int memfd_create(const char *name, unsigned int flags)
{
    return (int)syscall(SYS_memfd_create, name, flags);
}
#endif /* __ANDROID_API__ < 28 */

#endif /* __ANDROID__ */
