# Android native port — current engineering gate

This is a native SDL2/NDK port of the real Permafrost engine, not a web wrapper. The upstream engine is vendored under `engine/`; do not push changes to the upstream repository.

## Required order of work

1. **Android shell and SDL2:** use the SDL2 Android project template as the starting point, build ARM64 with GLES context creation, and confirm the native activity starts.
2. **Renderer portability:** replace desktop-only GLEW initialization with an Android/GLES loader strategy; gate or replace unsupported entry points instead of doing a blind header substitution.
3. **Shader portability:** classify every shader by GLSL version and feature requirements. Geometry shaders, compute shaders, SSBOs and image load/store cannot be assumed available in GLES 3.0.
4. **Native dependencies:** create an ARM64 build path for SDL2, Python 2.7 runtime, OpenAL Soft and allocator; the current engine Makefile is desktop-specific and is not an Android build recipe.
5. **Touch UX:** verify finger coordinates against SDL logical/drawable sizes; implement selection, drag/pan, pinch zoom, minimap interaction and in-game UI actions.
6. **Acceptance:** build a debug APK, preserve the APK as a workflow artifact, inspect startup logs, and test on the target phone. A CI green check alone is not device acceptance.

## Evidence rule

A source audit is not a compile. A successful desktop Linux build is not an Android build. A successful Android build is not proof the game renders or that the controls work on a phone. Report each milestone separately and do not claim an APK until the workflow actually produces one.

## Shell and build workspace (added 2026-10-20)

- `app/` — Gradle application module. `app/jni/Android.mk` builds the
  Stage 2 step 1 shell (`pf_android_shell.c` + vendored SDL2 2.30.0);
  `app/jni/Android-engine.mk` compiles the full engine (minus the Python
  2.7 scripting subsystem) as an arm64-v8a static library for the
  compile-report milestone.
- `include/pf_gl.h` — canonical portable GL entry header (desktop keeps
  GLEW; Android uses GLES 3.2 + GL_EXT_buffer_storage), installed next to
  the engine renderer sources by `scripts/patch-glew-gles.py`.
- `port-src/pf_gl_android.c` — runtime resolution of `glBufferStorage`
  through EGL for Android builds.
- `tests/sched_ctx_offsets.c` — static assertions pinning the AArch64
  fiber-context layout against `engine/src/context_switch.S`.

CI workflows: `android-shell-apk.yml` (debug APK artifact),
`android-engine-compile-report.yml` (per-file ARM64/GLES compile
evidence), `apply-android-port-patches.yml` (applies, idempotence-checks
and commits the GLES/scheduler patches).

Milestone status for the order above: step 1 has a buildable shell APK
(not yet device-verified); step 2 has a source-level, idempotent patch
and compile-level evidence; steps 3-6 remain open.
