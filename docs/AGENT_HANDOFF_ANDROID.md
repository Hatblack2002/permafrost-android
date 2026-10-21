# Permafrost Android — Agent Handoff / Project Map

> **Purpose:** This is the operational handoff for any coding agent or human who continues the Android port. Read this file before changing code. It records intent, verified state, failed attempts, what is actually fixed, what remains blocked, and the required next actions. It is deliberately separate from the general README.

**Last updated:** 2026-10-21 (GLES Shader Validation Milestone)  
**Repository:** https://github.com/Hatblack2002/permafrost-android  
**Working branch:** `fix/gles-clip-varying-and-assets`  
**Active PR:** https://github.com/Hatblack2002/permafrost-android/pull/5  
**Upstream engine:** https://github.com/eduard-permyakov/permafrost-engine  
**Pinned upstream baseline:** `083a99cace3eb047e7a3ccb7dc6b22eb78e3967f` (v1.18)

## 1. What we are trying to build

Port the real Permafrost RTS engine/game to Android ARM64, initially targeting the Samsung Galaxy S20 FE (Android 13+, Adreno GPU). This is not a mock-up or a separate demo: the goal is for the real engine to boot, load a real map, render it, and ultimately be playable with proper touch controls.

Core constraints:
- Keep the pinned upstream source identifiable and pristine; Android-specific work belongs in this repository as patches, adapters, glue, and packaging changes.
- Do not claim a successful game port from a shell-only APK, a compile-only report, or a successful link alone.
- Do not silently discard important engine functionality just to make a shader or build pass. If a feature is intentionally unavailable, record the trade-off and verify startup remains safe.
- Do not distribute game assets unless redistribution is licensed. Keep asset sourcing/licensing separate from engine code.
- Make changes testable and reproducible. Add regression tests for every class of bug fixed.

## 2. Current stage — be precise about evidence

**Current gate: All 44 GLES shaders verified (44/44 passed glslangValidator). Pushing fixes to trigger fresh CI game APK packaging and on-device runtime validation.**

Verified by CI on 2026-10-21:
- ARM64 native dependency job successfully cross-builds and packages CPython 2.7, mimalloc, and OpenAL Soft.
- Gradle 8.9 setup succeeds; the game job can download and verify the dependency artifact.
- Shader transformation and the dedicated clip-varying regression test both pass.
- The validator now continues through the shader tree and reports multiple failures in one run.
- The full APK build and upload are skipped because shader validation fails. **Do not link or recommend an older APK as if it contains these fixes.**

Latest relevant failed build:
- Run #50: https://github.com/Hatblack2002/permafrost-android/actions/runs/39664622756
- Run #51: https://github.com/Hatblack2002/permafrost-android/actions/runs/39664630699
- Build job ID for run #50: `119446977652`
- Result: dependency job passed; game job failed at **Validate every packaged GLES shader**. 31 shader files validated; 13 failed.

The port-status document contains historical milestones, some of which describe earlier successful APK builds. Those are historical evidence, not evidence that the current branch builds. Always check the exact commit SHA, workflow run conclusion, and artifact commit before sharing an APK.

## 3. What has been fixed (verified, not assumed)

### A. Literal newline in shader version transformation
- Commit: `871ebf1fd36818e6f6afa298bc92387877f91ea7`
- https://github.com/Hatblack2002/permafrost-android/commit/871ebf1fd36818e6f6afa298bc92387877f91ea7
- Root cause: `scripts/android-shader-es.py` wrote a literal backslash-n sequence instead of a real newline while moving the GLSL version directive.
- Correction: output now places `#version 320 es` on its own first line. The later regression test verifies this for transformed shaders.
- Evidence: the shader transformation test passes in the current CI run; shader validation gets past the earlier malformed-version error.

### B. Report all shader errors instead of stopping at the first one
- Commit: `26d2143119bb520eba5739f06bb56e6f0320e920`
- https://github.com/Hatblack2002/permafrost-android/commit/26d2143119bb520eba5739f06bb56e6f0320e920
- The workflow validation loop collects diagnostics across the shader set, allowing one run to reveal multiple independent GLES incompatibilities.

### C. Regression coverage for version directive placement
- Commit: `8859e19f89156786aecee20a80288d050c56af67`
- https://github.com/Hatblack2002/permafrost-android/commit/8859e19f89156786aecee20a80288d050c56af67
- `scripts/test-android-shader-es.py` checks the transformed shader files begin with the expected `#version 320 es` directive and that the escaped literal-newline bug does not return.
- Evidence: “Test GLES shader clip-varying transformation” passes in CI.

### D. ARM64 native dependency stage
- `scripts/build-deps-android.sh` builds CPython 2.7, mimalloc, and OpenAL Soft for arm64-v8a.
- The dependency job has passed in the latest relevant CI runs. This does **not** mean the engine APK builds.

## 4. Resolved shader validation errors (13/13 fixed and verified)

All 13 failing shaders identified in CI run #50 / run #52 have been fixed with minimal, semantically sound GLSL ES 3.20 corrections. 44 of 44 packaged shaders now pass `glslangValidator -S <stage>` without warnings or errors.

| Shader file | Root issue | Solution applied & verified |
|---|---|---|
| `vertex/statusbar.glsl` | float / int and float * int | Explicit float constants `(4.0 / 1080.0)` and `float(curr_res.y)` cast. |
| `fragment/statusbar.glsl` | same float/int arithmetic | Same explicit float constants and cast. |
| `fragment/textured-phong-shadowed.glsl` | missing `sampler2DArray` precision; `pow(float, int)` | Added `sampler2DArray` to `FRAG_PRECISION`; `#define SPECULAR_SHININESS 2.0`. |
| `fragment/billboard.glsl` | missing `sampler2DArray` precision | Injected `precision highp sampler2DArray;` via `scripts/android-shader-es.py`. |
| `fragment/billboard-depth.glsl` | missing `sampler2DArray` precision | Injected `precision highp sampler2DArray;` via `scripts/android-shader-es.py`. |
| `fragment/textured-phong-shadowed-batched.glsl` | missing `sampler2DArray` precision; `pow(float, int)` | Injected precision; `#define SPECULAR_SHININESS 2.0`. |
| `fragment/textured.glsl` | missing `sampler2DArray` precision | Injected `precision highp sampler2DArray;` via `scripts/android-shader-es.py`. |
| `fragment/terrain-shadowed.glsl` | missing `sampler2DArray` precision; `mod(int, int)`; `sqrt(int)`; `1.0 / ivec2` | Injected precision; `%` operator; `sqrt(float(...))`; `1.0 / vec2(textureSize(...))`. |
| `fragment/minimap.glsl` | float * int and float / int | Explicit float conversions for `chunk_w`, `chunk_h`, `tile_w`, `tile_h`. |
| `fragment/sprite-batched.glsl` | float/int coordinate calculations | Explicit float conversions for offsets, dimensions, and texture normalization. |
| `fragment/water.glsl` | float / int in map resolution math | Explicit float conversions `float(map_resolution.x/y/z/a)`. |
| `fragment/foliage.glsl` | float - int in chunk base coordinates | Explicit `float(chunk_c * chunk_x_dist)` conversion. |
| `compute/movement.glsl` | non-literal `layout(local_size_x = LANES)`; uint/int mismatches | Literal `layout(local_size_x = 64) in;`, `#define LANES 64u`, and `0u` loop initializers. | The diagnostics fall into four main classes:

| Shader file | Reported issue | What to investigate |
|---|---|---|
| `vertex/statusbar.glsl` | float divided by int and float multiplied by int (line 81) | Find the exact expressions/constants and use explicit, semantically correct float types. |
| `fragment/statusbar.glsl` | same float/int arithmetic class (line 88) | Fix type consistency; don't blanket-rewrite unrelated literals. |
| `fragment/textured-phong-shadowed.glsl` | sampler/image default precision missing (line 91) | Add the appropriate GLES default precision declaration for the sampler type actually used. |
| `fragment/billboard.glsl` | sampler/image default precision missing (line 68) | Same precision audit; inspect sampler type. |
| `fragment/billboard-depth.glsl` | sampler/image default precision missing (line 57) | Same precision audit; inspect sampler type. |
| `fragment/textured-phong-shadowed-batched.glsl` | sampler/image default precision missing (line 84) | Same precision audit; inspect sampler type. |
| `fragment/textured.glsl` | sampler/image default precision missing (line 73) | Same precision audit; inspect sampler type. |
| `fragment/terrain-shadowed.glsl` | sampler/image default precision missing (line 127) | Same precision audit; inspect sampler type. |
| `fragment/minimap.glsl` | float multiplied by int (line 96) | Make dimensions/indices and float calculations type-correct. |
| `fragment/sprite-batched.glsl` | float/int multiply/add and assignment mismatch (line 84) | Inspect the full expression and preserve intended coordinate math. |
| `fragment/water.glsl` | float divided by int (line 191) | Fix the operand type without changing intended scale. |
| `fragment/foliage.glsl` | float minus int (line 211) | Fix the operand type, then revalidate. |
| `compute/movement.glsl` | non-literal layout ID unsupported in GLES (line 58) | GLSL ES requires a compile-time literal for this layout qualifier; use a valid literal or redesign the binding assignment consistently with the engine's resource binding code. |

Note: glslang emits duplicate diagnostics because the workflow validates shader stages in more than one pass. The list above is the 13 unique failing files, not 13 individual diagnostic lines.

Important: do not assume adding `precision highp samplerBuffer;` fixes every “sampler/image” error. Determine whether the declaration is a `samplerBuffer`, `sampler2D`, `isamplerBuffer`, `usamplerBuffer`, or another opaque type, and add the matching precision qualifier where GLES requires it. The existing transformer already injects several precision declarations, but the current failures prove its coverage is incomplete.

## 5. Earlier runtime / architecture issues to keep on the radar

These are project-level risks, not necessarily the current CI blocker:
- Upstream renderer assumes desktop OpenGL 3.3 and GLEW. Android uses GLES; the port uses `android/include/pf_gl.h` and `android/port-src/pf_gl_android.c` to isolate compatibility shims.
- The engine uses compute shaders, SSBOs, geometry shaders, texture buffers, and compressed texture paths. Device extension/format support must be verified on the target GPU; successful glslang validation is not runtime driver proof.
- `gl_ClipDistance[0]` is not available in GLSL ES. The transform routes the clip value through a `pf_clip0` varying and paired fragment-stage discard. Preserve this behavior when changing shader interfaces.
- The AArch64 fiber scheduler required an ARM64 context-switch implementation; retain layout/static-assert tests.
- Embedded Python 2.7, its stdlib/import paths, mimalloc, OpenAL, asset extraction, basepath handling, SDL activity lifecycle, and fatal-startup reporting all need end-to-end verification.
- Previous device behavior included the app closing immediately. Boot diagnostics were added to expose logs on screen and write boot-report files. Do not assume that earlier startup issue is resolved unless a current device report proves it.
- Touch support is not complete. Real selection, raycast, camera, minimap, and order-command paths must receive touch input; decorative buttons are not acceptance.

## 6. Required next actions (in order)

1. **Fetch and inspect the current branch source for every failing shader.** Read enough surrounding code to understand variable types, macros, and resource-binding conventions. Do not patch from the error text alone.
2. **Fix the 13 unique shader failures in the source/transform layer**, not only generated APK copies. Prefer minimal, semantically correct edits. For sampler precision, inspect exact opaque types; for the compute layout, inspect how the engine binds that resource before choosing a literal.
3. **Add regression tests** for the specific error classes (precision qualifiers, mixed int/float arithmetic, and compile-time layout IDs) where practical. Avoid tests that merely encode the current implementation without checking GLES validity.
4. Run the transform unit test and validator locally/CI. The acceptance gate is zero failed shaders, not “the validator reached the end.”
5. After shader validation passes, follow the same workflow through asset/script packaging, native engine build/link, APK verification, `libmain.so` export check, and artifact upload. Check the exact commit SHA.
6. If the build fails after shaders, inspect the new failing step and logs; don't return to already-fixed issues without evidence.
7. Once a fresh APK is produced, verify its artifact belongs to the current commit, then install/run it on the target Android phone. Capture the on-screen boot report or `boot-report.txt`; use that evidence to address runtime initialization, shader compilation, SSBO, S3TC, audio, and map loading.
8. Only after the real map is rendered reliably should the project move to full touch controls, pause/resume, performance, memory, thermal, and release-readiness testing.

## 7. Build / evidence rules

- CI dependency success = native dependencies built. It is not an APK.
- Shell APK success = Android activity/GLES shell works. It is not the game.
- Engine compile success = source compiles. It is not a linked runnable game.
- APK build/link success = a package was created and native symbols linked. It is not proof the game starts.
- On-device boot success = engine startup progressed; still not proof of a playable map.
- Map/gameplay acceptance requires actual rendering and interaction on device with logs or reproducible observations.
- Never provide an APK download link unless the current workflow run has succeeded and its artifacts list contains the APK. Never substitute an old artifact without clearly labeling its commit and limitations.
- When handing off work, state the exact branch, commit SHA, workflow run URL, failing step, and observed errors. Separate facts from hypotheses.

## 8. Useful project files

- `README.md` — short project overview and guardrails.
- `docs/PORT_STATUS.md` — broader historical milestones and architecture notes; check dates and distinguish historical from current evidence.
- `docs/ANDROID_PORT_PLAN.md` — stage-by-stage porting plan and acceptance criteria.
- `scripts/android-shader-es.py` — desktop GLSL to GLES 3.2 transformation.
- `scripts/test-android-shader-es.py` — transformer regression tests.
- `.github/workflows/android-game-apk.yml` — dependency, shader validation, full-game APK build, artifact upload.
- `engine/src/render/gl_shader.c` — shader program initialization/failure handling.
- `android/app/jni/Android.mk` and `android/app/jni/src/pf_android_main.c` — engine native link and Android boot/diagnostic glue.
- `android/port-src/pf_gl_android.c`, `android/include/pf_gl.h` — Android GL compatibility layer.
- `scripts/build-deps-android.sh` — ARM64 dependency cross-build.

## 9. Working agreement for the next agent

Act autonomously: inspect the repository, reproduce the failure, read complete logs, map the error back to source, implement a minimal fix, add a regression test, run the relevant checks, and continue to the next blocker. Do not stop after the first error if CI can reveal more. Do not ask the user to diagnose compiler errors that the repository and logs already expose. Ask only when a decision genuinely requires product intent, unavailable device access, or a trade-off that cannot be resolved from source and tests.
