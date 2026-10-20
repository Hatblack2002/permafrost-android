/*
 * pf_android_shell.c — Permafrost Android shell smoke test.
 *
 * Milestone: Stage 2, step 1 of android/README.md — "Android shell and
 * SDL2: use the SDL2 Android project template as the starting point,
 * build ARM64 with GLES context creation, and confirm the native
 * activity starts."
 *
 * What this binary proves once it runs on a device:
 *   - the SDL2 Android activity integration works on arm64-v8a,
 *   - an OpenGL ES 3.2 context is created through SDL/EGL,
 *   - the render loop and swapchain behave (animated clear color),
 *   - lifecycle events (pause/resume) do not crash the shell.
 *
 * What this binary does NOT claim: this is not the engine. The engine
 * renderer/compilation milestones are tracked in docs/PORT_STATUS.md and
 * driven by android/app/jni/Android-engine.mk in CI.
 */
#include <SDL.h>
#include <GLES3/gl3.h>
/* ES 3.1 entry points (glDispatchCompute) live in gl31.h on the NDK;
 * gl3.h only covers ES 3.0. The context itself is still requested as
 * ES 3.2 below. */
#include <GLES3/gl31.h>

#include <stdbool.h>
#include <stdio.h>

static const char *gl_err_str(GLenum err)
{
    switch(err) {
    case GL_NO_ERROR:          return "GL_NO_ERROR";
    case GL_INVALID_ENUM:      return "GL_INVALID_ENUM";
    case GL_INVALID_VALUE:     return "GL_INVALID_VALUE";
    case GL_INVALID_OPERATION: return "GL_INVALID_OPERATION";
    case GL_OUT_OF_MEMORY:     return "GL_OUT_OF_MEMORY";
    default:                   return "unknown";
    }
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");

    if(SDL_Init(SDL_INIT_VIDEO) < 0) {
        SDL_Log("pf-shell: SDL_Init failed: %s", SDL_GetError());
        return 1;
    }

    /* Must match the port's GLES strategy in pf_gl.h / render.c:
     * an ES 3.2 context profile on Android. */
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_RED_SIZE, 8);
    SDL_GL_SetAttribute(SDL_GL_GREEN_SIZE, 8);
    SDL_GL_SetAttribute(SDL_GL_BLUE_SIZE, 8);
    SDL_GL_SetAttribute(SDL_GL_ALPHA_SIZE, 8);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);

    SDL_Window *window = SDL_CreateWindow(
        "Permafrost Android Shell",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        1280, 720,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if(!window) {
        SDL_Log("pf-shell: SDL_CreateWindow failed: %s", SDL_GetError());
        SDL_Quit();
        return 1;
    }

    SDL_GLContext ctx = SDL_GL_CreateContext(window);
    if(!ctx) {
        SDL_Log("pf-shell: GLES context creation failed: %s", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }

    SDL_GL_SetSwapInterval(1);

    const GLubyte *gl_ver = glGetString(GL_VERSION);
    const GLubyte *gl_ren = glGetString(GL_RENDERER);
    const GLubyte *gl_sl  = glGetString(GL_SHADING_LANGUAGE_VERSION);
    SDL_Log("pf-shell: GL_VERSION    = %s", gl_ver ? (const char*)gl_ver : "(null)");
    SDL_Log("pf-shell: GL_RENDERER   = %s", gl_ren ? (const char*)gl_ren : "(null)");
    SDL_Log("pf-shell: GLSL_VERSION  = %s", gl_sl  ? (const char*)gl_sl  : "(null)");

    int width = 0, height = 0;
    SDL_GL_GetDrawableSize(window, &width, &height);
    SDL_Log("pf-shell: drawable size = %dx%d", width, height);

    /* Verify a couple of ES 3.2 entry points the engine relies on. */
    SDL_Log("pf-shell: glDrawArraysInstanced=%p glTexImage3D=%p glDispatchCompute=%p",
        (void*)(uintptr_t)glDrawArraysInstanced,
        (void*)(uintptr_t)glTexImage3D,
        (void*)(uintptr_t)glDispatchCompute);

    Uint32 frame = 0;
    bool running = true;
    while(running) {
        SDL_Event event;
        while(SDL_PollEvent(&event)) {
            if(event.type == SDL_QUIT)
                running = false;
            else if(event.type == SDL_APP_TERMINATING)
                running = false;
            else if(event.type == SDL_WINDOWEVENT
                 && event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED) {
                SDL_GL_GetDrawableSize(window, &width, &height);
                SDL_Log("pf-shell: resize -> %dx%d", width, height);
            }
        }

        /* Animated clear color: visible proof the swapchain presents. */
        float t = (frame % 600) / 600.0f;
        float r = 0.1f + 0.3f * (0.5f + 0.5f * t);
        float b = 0.4f + 0.3f * (1.0f - t);
        glClearColor(r, 0.12f, b, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        GLenum gl_err = glGetError();
        if(gl_err != GL_NO_ERROR && (frame % 120) == 0)
            SDL_Log("pf-shell: GL error on frame %u: %s", frame,
                gl_err_str(gl_err));

        SDL_GL_SwapWindow(window);
        frame++;
    }

    SDL_Log("pf-shell: clean exit after %u frames", frame);
    SDL_GL_DeleteContext(ctx);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
