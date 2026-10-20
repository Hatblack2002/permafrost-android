# Port status

## Baseline

- Upstream: https://github.com/eduard-permyakov/permafrost-engine
- Pinned commit: `083a99cace3eb047e7a3ccb7dc6b22eb78e3967f` (version 1.18)
- Baseline source is kept pristine; Android changes must be patches in this repository.
- Use `scripts/prepare-upstream.sh` to materialize that exact upstream revision on a machine with Git/network access.

## Confirmed source-level blockers

1. `Makefile` defines only Linux and Windows targets. Linux links desktop GL and GLEW and builds bundled Python 2.7.
2. `src/render/render.c` creates an SDL GL context and initializes GLEW. Android needs an explicit GLES strategy; simply changing compiler flags is insufficient.
3. `src/map/raycast.c` derives world-space picking rays from `SDL_GetMouseState`.
4. `src/cursor.c`, `src/map/minimap.c`, `src/cam_control.c`, and `src/game/selection.c` contain mouse-centric paths.
5. The first Android input change must establish one pointer-coordinate/event abstraction used by raycasting and the game systems; touch gestures must not be fake UI.

## Next implementation order

1. Get an Android ARM64 SDL2 activity/window and GLES context.
2. Resolve GLEW/OpenGL 3.3 and shader compatibility before attempting a full engine build.
3. Introduce touch pointer coordinates and route tap/drag/pinch into actual selection, camera, minimap, and order systems.
4. Validate with a real map on device; only then optimize UI and performance.

## Progress log

### 2026-10-20 — GLES portability, AArch64 scheduler, Android shell

Completed (compile-level evidence only; no device claims):

- **GLES portability layer** (`scripts/patch-glew-gles.py`):
  `android/include/pf_gl.h` keeps desktop GLEW behavior unchanged and maps
  `__ANDROID__` builds to GLES 3.2 (compute + SSBO are GLES 3.1 core,
  geometry shaders/texture buffers/KHR_debug are GLES 3.2 core). The 22
  engine files that included `<GL/glew.h>` now include `pf_gl.h`;
  `render.c` GLEW init/version checks and the context-attribute profile
  are gated by `__ANDROID__`; `glBufferStorage` resolves through
  `GL_EXT_buffer_storage` (`android/port-src/pf_gl_android.c`).
- **AArch64 scheduler port** (`scripts/patch-sched-arm64.py`): the
  upstream fiber scheduler was x86_64-only. `context_switch.S` gained an
  `__aarch64__` branch (callee-saved x19-x28/fp/lr/sp + d8-d15,
  fpsr/fpcr) and `sched.c` gained the matching `struct context` plus an
  entry trampoline (x0 carries the switch return value, so the task
  argument travels via x17 and x19). Layout is pinned by
  `android/tests/sched_ctx_offsets.c` static assertions.
- **Android shell** (`android/`): Gradle + ndk-build module reusing the
  vendored SDL2 2.30.0 activity glue; `pf_android_shell.c` proves
  activity + GLES 3.2 context + present loop (shell smoke APK; NOT the
  engine). `Android-engine.mk` compiles the full engine (minus the
  Python 2.7 scripting subsystem) as an arm64-v8a static library for the
  compile-report milestone.
- **CI**: `android-shell-apk.yml` (debug APK artifact),
  `android-engine-compile-report.yml` (per-file compile evidence),
  `apply-android-port-patches.yml` (applies + idempotence-checks +
  commits the GLES/scheduler patches). All workflows YAML-validated.

Remaining blockers, in order:

1. ARM64 build of the embedded Python 2.7 runtime (`deps/Python`) so
   `src/script/py_*.c` compiles and `S_Init` can succeed.
2. Engine link: mimalloc/OpenAL Soft ARM64 static/shared builds, assets
   and shader packaging into APK assets, basepath resolution on Android.
3. On-device acceptance of the shell APK (Galaxy S20 FE), then engine
   boot validation; shader 430/SSBO and S3TC-compression runtime checks.
